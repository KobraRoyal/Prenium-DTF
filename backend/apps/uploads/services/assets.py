from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max

from apps.auditlog.services import record_event
from apps.b2b_order_projects.services.transitions import B2BOrderProjectTransitionPolicy
from apps.uploads.models import Asset, AssetVersion
from apps.uploads.services.validation import UploadValidationService


@dataclass(frozen=True)
class AssetDomainError(Exception):
    code: str
    message: str
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        return self.message


class AssetService:
    def __init__(self):
        self.validation = UploadValidationService()
        self.transitions = B2BOrderProjectTransitionPolicy()

    @transaction.atomic
    def create_asset(
        self,
        *,
        customer,
        actor,
        name,
        uploaded_file,
        source: str,
        auto_size_requested: bool = False,
        schedule_analysis: bool = True,
        metadata: dict | None = None,
    ) -> AssetVersion:
        """Crée un asset client sans le coupler à un projet de commande."""
        cleaned_name = str(name or getattr(uploaded_file, "name", "Visuel")).strip()
        asset = Asset.objects.create(
            customer=customer,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
            name=(cleaned_name or "Visuel")[:255],
        )
        version = self._create_version(
            asset=asset,
            actor=actor,
            uploaded_file=uploaded_file,
            replaced_version=None,
            auto_size_requested=auto_size_requested,
        )
        asset.current_version = version
        asset.save(update_fields=["current_version", "updated_at"])
        self._audit(
            "created",
            asset=asset,
            version=version,
            actor=actor,
            source=source,
            metadata=metadata,
        )
        if schedule_analysis:
            transaction.on_commit(lambda: self.schedule_analysis(version=version))
        return version

    @transaction.atomic
    def create_production_asset(
        self,
        *,
        customer,
        actor,
        name,
        uploaded_file,
        source: str,
        metadata: dict | None = None,
    ) -> AssetVersion:
        """Crée le livrable HD puis lance les contrôles qualité du workflow commande."""
        production_metadata = {
            **(metadata or {}),
            "production_output": True,
        }
        return self.create_asset(
            customer=customer,
            actor=actor,
            name=name,
            uploaded_file=uploaded_file,
            source=source,
            auto_size_requested=False,
            schedule_analysis=True,
            metadata=production_metadata,
        )

    @transaction.atomic
    def attach_project_item_file(
        self,
        *,
        project,
        item_public_id,
        actor,
        uploaded_file,
        source: str,
        auto_size_requested: bool = False,
    ) -> AssetVersion:
        locked_project = type(project).objects.select_for_update().get(pk=project.pk)
        self._ensure_project_editable(locked_project)
        item = (
            locked_project.items.select_for_update()
            .filter(customer=locked_project.customer, public_id=item_public_id)
            .first()
        )
        if item is None:
            raise AssetDomainError("PROJECT_ITEM_NOT_FOUND", "Ligne de projet introuvable.")
        if item.asset_id:
            raise AssetDomainError(
                "ASSET_ALREADY_ATTACHED",
                "Un fichier est déjà rattaché. Utilisez le remplacement versionné.",
            )

        asset = Asset.objects.create(
            customer=locked_project.customer,
            created_by=actor,
            name=item.name,
        )
        version = self._create_version(
            asset=asset,
            actor=actor,
            uploaded_file=uploaded_file,
            replaced_version=None,
            auto_size_requested=auto_size_requested,
        )
        asset.current_version = version
        asset.save(update_fields=["current_version", "updated_at"])
        item.asset = asset
        item.save(update_fields=["asset", "updated_at"])
        self._refresh_project(locked_project)
        self._audit(
            "attached",
            asset=asset,
            version=version,
            actor=actor,
            source=source,
            metadata={
                "project_public_id": str(locked_project.public_id),
                "item_public_id": str(item.public_id),
            },
        )
        transaction.on_commit(lambda: self.schedule_analysis(version=version))
        return version

    @transaction.atomic
    def replace_project_item_file(
        self,
        *,
        project,
        item_public_id,
        actor,
        uploaded_file,
        source: str,
    ) -> AssetVersion:
        locked_project = type(project).objects.select_for_update().get(pk=project.pk)
        self._ensure_project_editable(locked_project)
        item = (
            locked_project.items.select_for_update()
            .filter(customer=locked_project.customer, public_id=item_public_id)
            .first()
        )
        if item is None or item.asset_id is None:
            raise AssetDomainError("ASSET_NOT_FOUND", "Aucun fichier à remplacer pour cette ligne.")
        from apps.b2b_order_projects.models import B2BOrderProject

        is_gang_sheet_output = (
            locked_project.order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET
        )
        if not is_gang_sheet_output:
            from apps.gang_sheets.models import GangSheet

            is_gang_sheet_output = GangSheet.objects.filter(
                customer=locked_project.customer,
                production_asset_id=item.asset_id,
            ).exists()
        if is_gang_sheet_output:
            raise AssetDomainError(
                "PRODUCTION_ASSET_LOCKED",
                "Le fichier final de cette planche est verrouillé pour la production.",
            )
        asset = Asset.objects.select_for_update().get(
            pk=item.asset_id,
            customer=locked_project.customer,
        )
        previous = (
            AssetVersion.objects.select_for_update()
            .filter(
                pk=asset.current_version_id,
                customer=locked_project.customer,
            )
            .first()
        )
        if previous is None:
            raise AssetDomainError("ASSET_NOT_FOUND", "Aucun fichier à remplacer pour cette ligne.")
        if previous.analysis_status != AssetVersion.AnalysisStatus.PENDING:
            raise AssetDomainError(
                "ASSET_REPLACEMENT_CLOSED",
                "Le fichier ne peut plus être remplacé dès que son analyse a commencé.",
            )
        version = self._create_version(
            asset=asset,
            actor=actor,
            uploaded_file=uploaded_file,
            replaced_version=previous,
        )
        asset.current_version = version
        asset.save(update_fields=["current_version", "updated_at"])
        item.client_confirmed_asset_version = None
        item.client_confirmed_at = None
        item.client_confirmed_by = None
        item.save(
            update_fields=[
                "client_confirmed_asset_version",
                "client_confirmed_at",
                "client_confirmed_by",
                "updated_at",
            ]
        )
        self._refresh_project(locked_project)
        self._audit(
            "version_replaced",
            asset=asset,
            version=version,
            actor=actor,
            source=source,
            metadata={
                "project_public_id": str(locked_project.public_id),
                "item_public_id": str(item.public_id),
                "previous_version_public_id": str(previous.public_id) if previous else None,
            },
        )
        transaction.on_commit(lambda: self.schedule_analysis(version=version))
        return version

    @staticmethod
    def can_replace_project_item_file(*, item) -> bool:
        asset = getattr(item, "asset", None)
        version = getattr(asset, "current_version", None) if asset else None
        return bool(version and version.analysis_status == AssetVersion.AnalysisStatus.PENDING)

    def get_project_item_version(self, *, project, item_public_id):
        item = (
            project.items.filter(customer=project.customer, public_id=item_public_id)
            .select_related("asset", "asset__current_version", "asset__current_version__analysis")
            .first()
        )
        if item is None:
            return None, None
        if item.asset is None:
            return item, None
        return item, item.asset.current_version

    def prepare_project_download(self, *, project, item_public_id, actor, source: str):
        item, version = self.get_project_item_version(
            project=project,
            item_public_id=item_public_id,
        )
        if item is None or version is None:
            return None
        self._audit(
            "downloaded",
            asset=item.asset,
            version=version,
            actor=actor,
            source=source,
            metadata={
                "project_public_id": str(project.public_id),
                "item_public_id": str(item.public_id),
            },
        )
        return version

    @transaction.atomic
    def link_existing_asset_to_item(
        self,
        *,
        project,
        item_public_id,
        asset,
        actor,
        source: str,
    ):
        locked_project = type(project).objects.select_for_update().get(pk=project.pk)
        self._ensure_project_editable(locked_project)
        item = (
            locked_project.items.select_for_update()
            .filter(customer=locked_project.customer, public_id=item_public_id)
            .first()
        )
        if item is None:
            raise AssetDomainError("PROJECT_ITEM_NOT_FOUND", "Ligne de projet introuvable.")
        if item.asset_id:
            raise AssetDomainError(
                "ASSET_ALREADY_ATTACHED",
                "Un fichier est déjà rattaché à cette ligne.",
            )
        if asset.customer_id != locked_project.customer_id:
            raise AssetDomainError("ASSET_NOT_FOUND", "Fichier introuvable pour ce client.")

        item.asset = asset
        item.save(update_fields=["asset", "updated_at"])
        self._refresh_project(locked_project)
        version = asset.current_version
        self._audit(
            "linked",
            asset=asset,
            version=version,
            actor=actor,
            source=source,
            metadata={
                "project_public_id": str(locked_project.public_id),
                "item_public_id": str(item.public_id),
            },
        )
        return item

    def prepare_project_preview(self, *, project, item_public_id):
        item, version = self.get_project_item_version(
            project=project,
            item_public_id=item_public_id,
        )
        if item is None or version is None:
            return None
        return self.prepare_version_preview(version=version)

    def prepare_project_thin_zone_overlay(self, *, project, item_public_id):
        item, version = self.get_project_item_version(
            project=project,
            item_public_id=item_public_id,
        )
        if item is None or version is None:
            return None
        analysis = getattr(version, "analysis", None)
        if analysis is None or not analysis.thin_zone_overlay:
            return None
        thin_zone = (analysis.metadata or {}).get("thin_zone") or {}
        if not thin_zone.get("detected"):
            return None
        return analysis.thin_zone_overlay, "image/webp"

    def prepare_project_semi_transparency_overlay(self, *, project, item_public_id):
        item, version = self.get_project_item_version(
            project=project,
            item_public_id=item_public_id,
        )
        if item is None or version is None:
            return None
        analysis = getattr(version, "analysis", None)
        if analysis is None or not analysis.semi_transparency_overlay:
            return None
        semi_transparency = (analysis.metadata or {}).get("semi_transparency") or {}
        if not semi_transparency.get("detected"):
            return None
        return analysis.semi_transparency_overlay, "image/webp"

    def prepare_order_upload_preview(self, *, order_upload):
        version = getattr(order_upload, "asset_version", None)
        if version is not None:
            return self.prepare_version_preview(version=version)
        if order_upload.mime_type in {"image/png", "image/jpeg", "image/webp", "image/gif"}:
            return order_upload.file, order_upload.mime_type
        return self._render_upload_file_preview(order_upload=order_upload)

    def prepare_version_preview(self, *, version):
        analysis = getattr(version, "analysis", None)
        if analysis is not None and analysis.thumbnail:
            return analysis.thumbnail, "image/webp"
        if version.mime_type in {"image/png", "image/jpeg", "image/webp"}:
            return version.file, version.mime_type
        try:
            from apps.uploads.services.asset_preview import AssetPreviewRenderer

            rendered = AssetPreviewRenderer().render(version=version)
            buffer = BytesIO()
            preview = rendered.image.copy()
            if preview.mode not in {"RGB", "RGBA"}:
                preview = preview.convert("RGBA")
            preview.save(buffer, format="WEBP", quality=85)
            preview.close()
            rendered.image.close()
            buffer.seek(0)
            return ContentFile(buffer.read(), name="preview.webp"), "image/webp"
        except Exception:
            return None

    def _render_upload_file_preview(self, *, order_upload):
        try:
            from apps.uploads.services.asset_preview import AssetPreviewRenderer

            class _UploadPreviewVersion:
                def __init__(self, upload):
                    self.file = upload.file
                    self.original_filename = upload.original_filename
                    self.mime_type = upload.mime_type

            rendered = AssetPreviewRenderer().render(version=_UploadPreviewVersion(order_upload))
            buffer = BytesIO()
            preview = rendered.image.copy()
            if preview.mode not in {"RGB", "RGBA"}:
                preview = preview.convert("RGBA")
            preview.save(buffer, format="WEBP", quality=85)
            preview.close()
            rendered.image.close()
            buffer.seek(0)
            return ContentFile(buffer.read(), name="preview.webp"), "image/webp"
        except Exception:
            return None

    def schedule_analysis(self, *, version: AssetVersion) -> None:
        from apps.uploads.tasks import analyze_asset_version_task

        analyze_asset_version_task.delay(str(version.public_id))

    def effective_dpi_for_item(self, *, item) -> float | None:
        version = getattr(getattr(item, "asset", None), "current_version", None)
        analysis = getattr(version, "analysis", None) if version else None
        if analysis is None or not analysis.image_width or not analysis.image_height:
            return None

        metadata = analysis.metadata or {}
        if metadata.get("dimension_basis") == "page" and not analysis.dpi_x and not analysis.dpi_y:
            return None

        width_inches = float(item.width_mm) / 25.4
        height_inches = float(item.height_mm) / 25.4
        if width_inches <= 0 or height_inches <= 0:
            return None

        print_effective = round(
            min(analysis.image_width / width_inches, analysis.image_height / height_inches),
            2,
        )

        if metadata.get("uses_artboard_dimensions") and metadata.get("has_vector_artwork"):
            placement_dpi = metadata.get("placement_effective_dpi") or analysis.dpi_x
            if placement_dpi:
                return round(float(placement_dpi), 2)

        if metadata.get("uses_artboard_dimensions") and analysis.dpi_x:
            return print_effective

        if analysis.dpi_x and analysis.dpi_y:
            intrinsic_width_in = float(analysis.image_width) / float(analysis.dpi_x)
            intrinsic_height_in = float(analysis.image_height) / float(analysis.dpi_y)
            if self._print_size_matches(
                width_inches=width_inches,
                height_inches=height_inches,
                intrinsic_width_in=intrinsic_width_in,
                intrinsic_height_in=intrinsic_height_in,
            ):
                return round(min(float(analysis.dpi_x), float(analysis.dpi_y)), 2)

        return round(
            min(analysis.image_width / width_inches, analysis.image_height / height_inches),
            2,
        )

    @staticmethod
    def _print_size_matches(
        *,
        width_inches: float,
        height_inches: float,
        intrinsic_width_in: float,
        intrinsic_height_in: float,
        tolerance_ratio: float = 0.02,
    ) -> bool:
        if intrinsic_width_in <= 0 or intrinsic_height_in <= 0:
            return False
        width_delta = abs(width_inches - intrinsic_width_in) / intrinsic_width_in
        height_delta = abs(height_inches - intrinsic_height_in) / intrinsic_height_in
        return width_delta <= tolerance_ratio and height_delta <= tolerance_ratio

    @staticmethod
    def _is_vector_document(analysis) -> bool:
        if analysis is None:
            return False
        metadata = analysis.metadata or {}
        if metadata.get("dimension_basis") == "page" and not analysis.dpi_x and not analysis.dpi_y:
            return True
        format_name = str(metadata.get("format", "")).upper()
        return format_name in {"EPS", "AI"} and not analysis.dpi_x and not analysis.dpi_y

    def technical_review_for_item(self, *, item) -> dict[str, object]:
        version = getattr(getattr(item, "asset", None), "current_version", None)
        analysis = getattr(version, "analysis", None) if version else None
        effective_dpi = self.effective_dpi_for_item(item=item)
        recommended_dpi = int(getattr(settings, "B2B_RECOMMENDED_DPI", 300))
        minimum_dpi = int(getattr(settings, "B2B_MIN_ACCEPTABLE_DPI", 200))
        confirmed = bool(
            version
            and item.client_confirmed_asset_version_id
            and item.client_confirmed_asset_version_id == version.id
        )
        is_vector = self._is_vector_document(analysis)
        metadata = (analysis.metadata or {}) if analysis else {}
        thin_zone = dict(metadata.get("thin_zone") or {})
        semi_transparency = dict(metadata.get("semi_transparency") or {})

        if version is None or version.analysis_status in {"pending", "processing"}:
            level = "pending"
            label = "Analyse en cours"
            message = "Largeur, hauteur et résolution remontent automatiquement."
            resolution_display = "—"
        elif version.analysis_status == "failed":
            level = "error"
            label = "Analyse impossible"
            message = "Remplacez le fichier ou contactez l’atelier avant de continuer."
            resolution_display = "—"
        elif is_vector:
            level = "good"
            label = "Résolution OK"
            message = "Document vectoriel · netteté indépendante d’un DPI raster."
            resolution_display = "OK"
        elif effective_dpi is None:
            level = "warning"
            label = "Résolution à vérifier"
            message = "La résolution effective n’a pas pu être calculée automatiquement."
            resolution_display = "À vérifier"
        elif metadata.get("uses_artboard_dimensions") and metadata.get("has_vector_artwork"):
            raster_dpi = float(metadata.get("placement_effective_dpi") or analysis.dpi_x or 0)
            resolution_display = f"{raster_dpi:.0f} DPI" if raster_dpi else "OK"
            if raster_dpi >= recommended_dpi:
                level = "good"
                label = "Résolution OK"
                message = f"Document mixte · vectoriel net · photo raster {raster_dpi:.0f} DPI."
            elif raster_dpi >= minimum_dpi:
                level = "warning"
                label = "Résolution acceptable"
                message = (
                    f"Document mixte · photo raster {raster_dpi:.0f} DPI · "
                    f"objectif {recommended_dpi} DPI."
                )
            else:
                level = "error"
                label = "Résolution insuffisante"
                message = (
                    f"Document mixte · photo raster {raster_dpi:.0f} DPI · "
                    f"pixellisation probable sous {minimum_dpi} DPI."
                )
        elif metadata.get("uses_artboard_dimensions") and analysis and analysis.dpi_x:
            source_dpi = float(analysis.dpi_x)
            resolution_display = f"{source_dpi:.0f} DPI"
            if effective_dpi >= minimum_dpi:
                level = "good" if effective_dpi >= recommended_dpi else "warning"
                label = "Résolution optimale" if level == "good" else "Résolution acceptable"
                message = (
                    f"{source_dpi:.0f} DPI source · {effective_dpi:.0f} DPI effectifs "
                    f"à l’échelle du document."
                )
            else:
                level = "error"
                label = "Résolution insuffisante"
                message = (
                    f"{source_dpi:.0f} DPI source · {effective_dpi:.0f} DPI effectifs "
                    f"à l’échelle du document · pixellisation probable sur la photo raster."
                )
        elif effective_dpi >= recommended_dpi:
            level = "good"
            label = "Résolution optimale"
            message = f"{effective_dpi:.0f} DPI effectifs · objectif {recommended_dpi} DPI atteint."
            resolution_display = f"{effective_dpi:.0f} DPI"
        elif effective_dpi >= minimum_dpi:
            level = "warning"
            label = "Résolution acceptable"
            message = (
                f"{effective_dpi:.0f} DPI effectifs · netteté potentiellement réduite "
                f"sous {recommended_dpi} DPI."
            )
            resolution_display = f"{effective_dpi:.0f} DPI"
        else:
            level = "error"
            label = "Résolution insuffisante"
            message = (
                f"{effective_dpi:.0f} DPI effectifs · pixellisation probable sous "
                f"{minimum_dpi} DPI."
            )
            resolution_display = f"{effective_dpi:.0f} DPI"

        issues = [
            issue
            for issue in (getattr(analysis, "warnings", []) or [])
            if issue and not str(issue).startswith("Aperçu généré")
        ]
        placement_dpi = metadata.get("placement_effective_dpi")
        source_dpi = float(analysis.dpi_x) if analysis and analysis.dpi_x else None
        if (
            placement_dpi
            and source_dpi
            and float(placement_dpi) < source_dpi * 0.85
            and metadata.get("dpi_source") == "embedded"
        ):
            issues.append(
                "Le visuel est étiré dans le PDF : la résolution native embarquée "
                f"({source_dpi:.0f} DPI) est supérieure à la résolution à la taille posée "
                f"({float(placement_dpi):.0f} DPI)."
            )
        if thin_zone.get("detected"):
            issues.append(
                "Des détails imprimés inférieurs à 0,5 mm ont été détectés et sont "
                "surlignés en rouge dans l’aperçu."
            )
        if semi_transparency.get("detected"):
            issues.append(
                "Des zones semi-transparentes ont été détectées (anti-alias, ombres, "
                "dégradés) et sont surlignées en orange dans l’aperçu. En DTF, ces "
                "pixels peuvent produire un rendu irrégulier ou un halo après pressage."
            )

        return {
            "level": level,
            "label": label,
            "message": message,
            "effective_dpi": effective_dpi,
            "resolution_display": resolution_display,
            "is_vector": is_vector,
            "recommended_dpi": recommended_dpi,
            "minimum_dpi": minimum_dpi,
            "issues": issues,
            "thin_zone": {
                "detected": bool(thin_zone.get("detected")),
                "threshold_mm": thin_zone.get("threshold_mm", 0.5),
                "coverage_percent": thin_zone.get("coverage_percent", 0.0),
            },
            "semi_transparency": {
                "detected": bool(semi_transparency.get("detected")),
                "coverage_percent": semi_transparency.get("coverage_percent", 0.0),
                "pixel_count": semi_transparency.get("pixel_count", 0),
            },
            "confirmed": confirmed,
            "can_confirm": bool(
                version and version.analysis_status in {"ready", "warning"} and analysis
            ),
            "version_public_id": str(version.public_id) if version else None,
        }

    def production_review_for_item(self, *, item) -> dict[str, object]:
        """Conserve les contrôles qualité du PDF HD sans recalculer sa résolution globale."""
        version = getattr(getattr(item, "asset", None), "current_version", None)
        review = self.technical_review_for_item(item=item)
        if version is None or version.analysis_status not in {
            AssetVersion.AnalysisStatus.READY,
            AssetVersion.AnalysisStatus.WARNING,
        }:
            return review

        review.update(
            {
                "level": "warning" if review["issues"] else "good",
                "label": "Contrôle du fichier HD",
                "message": (
                    "PDF HD hybride · vectoriel, mixte et raster préservés · contrôlez "
                    "les détails fins, les semi-transparences et la couleur du support."
                ),
                "effective_dpi": None,
                "resolution_display": "PDF hybride",
            }
        )
        return review

    def _create_version(
        self,
        *,
        asset,
        actor,
        uploaded_file,
        replaced_version,
        auto_size_requested=False,
    ):
        try:
            validated = self.validation.validate_uploaded_file(uploaded_file)
        except ValidationError as error:
            message = error.messages[0] if error.messages else "Fichier invalide."
            raise AssetDomainError("INVALID_ASSET_FILE", message) from None
        next_number = (
            AssetVersion.objects.for_asset(asset).aggregate(value=Max("version_number"))["value"]
            or 0
        ) + 1
        sha256 = self._sha256(validated.uploaded_file)
        version = AssetVersion(
            customer=asset.customer,
            asset=asset,
            uploaded_by=actor,
            replaced_version=replaced_version,
            version_number=next_number,
            original_filename=validated.original_filename,
            mime_type=validated.mime_type,
            size_bytes=validated.size_bytes,
            sha256=sha256,
            auto_size_requested=auto_size_requested,
        )
        version.file.save(
            validated.original_filename,
            validated.uploaded_file,
            save=False,
        )
        version.save()
        return version

    def _sha256(self, uploaded_file) -> str:
        digest = hashlib.sha256()
        uploaded_file.seek(0)
        if hasattr(uploaded_file, "chunks"):
            for chunk in uploaded_file.chunks():
                digest.update(chunk)
        else:
            while chunk := uploaded_file.read(64 * 1024):
                digest.update(chunk)
        uploaded_file.seek(0)
        return digest.hexdigest()

    def _ensure_project_editable(self, project):
        if not self.transitions.is_editable(project.status):
            raise AssetDomainError(
                "PROJECT_NOT_EDITABLE",
                "Les fichiers ne peuvent plus être modifiés dans ce statut.",
                {"current_status": project.status},
            )

    def _refresh_project(self, project):
        from apps.b2b_order_projects.services import B2BOrderProjectService

        B2BOrderProjectService().refresh_completeness(project=project)

    def _audit(self, event, *, asset, version, actor, source, metadata=None):
        record_event(
            action=f"asset.{event}",
            actor=actor,
            target=asset,
            metadata={
                "customer_public_id": str(asset.customer.public_id),
                "asset_public_id": str(asset.public_id),
                "asset_version_public_id": str(version.public_id),
                "version_number": version.version_number,
                "mime_type": version.mime_type,
                "size_bytes": version.size_bytes,
                "source": source,
                **(metadata or {}),
            },
        )
