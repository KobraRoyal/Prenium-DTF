from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services.projects import B2BOrderProjectService
from apps.gang_sheets.models import (
    GangSheet,
    GangSheetItem,
    GangSheetSiteSettings,
    GangSheetSourceAsset,
)
from apps.gang_sheets.services.drive import GangSheetDriveSyncService
from apps.gang_sheets.services.geometry import GangSheetGeometryService, normalize_rotation
from apps.orders.services.pricing import OrderPricingService
from apps.uploads.models import AssetVersion
from apps.uploads.services.assets import AssetDomainError, AssetService

HUNDREDTH = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")
MAX_BATCH_OCCURRENCES = 200
MAX_SOURCE_ASSETS = 100


class GangSheetDomainError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class GangSheetService:
    editable_statuses = {
        GangSheet.Status.DRAFT,
        GangSheet.Status.READY,
        GangSheet.Status.RENDER_FAILED,
    }

    def __init__(
        self,
        *,
        geometry=None,
        pricing=None,
        assets=None,
        projects=None,
        drive_sync=None,
    ):
        self.geometry = geometry or GangSheetGeometryService()
        self.pricing = pricing or OrderPricingService()
        self.assets = assets or AssetService()
        self.projects = projects or B2BOrderProjectService()
        self.drive_sync = drive_sync or GangSheetDriveSyncService()

    def list_customer_sheets(self, customer):
        return GangSheet.objects.for_customer(customer).select_related(
            "project",
            "order",
            "drive_sync",
        )

    def attach_can_delete(self, sheets):
        for sheet in sheets:
            sheet.can_delete = self.can_client_delete(sheet)
        return sheets

    def can_client_delete(self, sheet) -> bool:
        editable_standalone = (
            sheet.status in self.editable_statuses
            and not sheet.project_id
            and not sheet.order_id
            and not sheet.production_asset_id
        )
        drive_sync = getattr(sheet, "drive_sync", None)
        drive_secured = not settings.GOOGLE_DRIVE_SYNC_ENABLED or bool(
            drive_sync
            and drive_sync.status == drive_sync.Status.SYNCED
            and drive_sync.drive_file_id
            and drive_sync.revision == sheet.revision
        )
        secured_in_order_project = (
            sheet.status == GangSheet.Status.VALIDATED
            and sheet.project_id
            and sheet.production_asset_id
            and sheet.project.order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET
            and sheet.project.items.filter(
                customer=sheet.customer,
                asset_id=sheet.production_asset_id,
            ).exists()
            and drive_secured
            and (not sheet.order_id or sheet.project.converted_order_id == sheet.order_id)
        )
        return bool(editable_standalone or secured_in_order_project)

    def get_customer_sheet(self, *, customer, sheet_public_id):
        return (
            GangSheet.objects.for_customer(customer)
            .select_related("project", "order", "customer", "drive_sync")
            .prefetch_related("items__asset_version__asset", "source_assets__asset")
            .filter(public_id=sheet_public_id)
            .first()
        )

    def available_asset_versions(self, *, sheet):
        return (
            AssetVersion.objects.for_customer(sheet.customer)
            .filter(
                asset__gang_sheet_sources__sheet=sheet,
                asset__gang_sheet_sources__customer=sheet.customer,
                asset__current_version=models.F("pk"),
                asset__is_archived=False,
                analysis_status__in=(
                    AssetVersion.AnalysisStatus.READY,
                    AssetVersion.AnalysisStatus.WARNING,
                ),
            )
            .select_related("asset", "analysis")
            .distinct()
            .order_by("asset__name")
        )

    def source_asset_entries(self, *, sheet):
        return (
            GangSheetSourceAsset.objects.for_sheet(sheet)
            .select_related("asset", "asset__current_version", "asset__current_version__analysis")
            .filter(asset__is_archived=False)
        )

    @transaction.atomic
    def create_sheet(
        self,
        *,
        actor,
        name: str,
        customer=None,
        project=None,
        source: str = "client_portal",
    ):
        customer = customer or getattr(project, "customer", None)
        if customer is None:
            raise GangSheetDomainError("CUSTOMER_REQUIRED", "Le client est obligatoire.")
        cleaned_name = str(name or "").strip() or "Nouvelle planche"
        config = GangSheetSiteSettings.current()
        unit_price = self._unit_price(customer)
        sheet = GangSheet.objects.create(
            customer=customer,
            project=project,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
            name=cleaned_name[:255],
            width_mm=config.roll_width_mm,
            height_mm=config.minimum_height_mm,
            minimum_height_mm=config.minimum_height_mm,
            maximum_height_mm=config.maximum_height_mm,
            height_step_mm=config.height_step_mm,
            margin_mm=config.margin_mm,
            item_spacing_mm=config.item_spacing_mm,
            unit_price_eur=unit_price,
        )
        if project is not None:
            seen_asset_ids = set()
            source_assets = []
            for item in project.items.select_related("asset").filter(asset__isnull=False):
                if item.asset_id in seen_asset_ids:
                    continue
                seen_asset_ids.add(item.asset_id)
                source_assets.append(
                    GangSheetSourceAsset(
                        customer=customer,
                        sheet=sheet,
                        asset=item.asset,
                        added_by=actor if getattr(actor, "is_authenticated", False) else None,
                        width_mm=item.width_mm,
                        height_mm=item.height_mm,
                        sort_order=len(source_assets) + 1,
                    )
                )
            GangSheetSourceAsset.objects.bulk_create(source_assets)
        self._refresh_totals(sheet, [])
        self._audit("created", sheet=sheet, actor=actor, source=source)
        return sheet

    @transaction.atomic
    def upload_source_asset(
        self,
        *,
        sheet,
        actor,
        uploaded_file,
        source="client_portal",
    ):
        locked = self._lock_editable(sheet)
        if locked.source_assets.count() >= MAX_SOURCE_ASSETS:
            raise GangSheetDomainError(
                "SOURCE_ASSET_LIMIT",
                f"Une galerie est limitée à {MAX_SOURCE_ASSETS} fichiers.",
            )
        asset_name = Path(str(getattr(uploaded_file, "name", "Visuel"))).stem or "Visuel"
        try:
            version = self.assets.create_asset(
                customer=locked.customer,
                actor=actor,
                name=asset_name,
                uploaded_file=uploaded_file,
                source=source,
                auto_size_requested=True,
                metadata={"gang_sheet_public_id": str(locked.public_id)},
            )
        except AssetDomainError as error:
            raise GangSheetDomainError(error.code, error.message, error.details) from error
        next_position = (locked.source_assets.aggregate(value=Max("sort_order"))["value"] or 0) + 1
        source_asset = GangSheetSourceAsset.objects.create(
            customer=locked.customer,
            sheet=locked,
            asset=version.asset,
            added_by=actor if getattr(actor, "is_authenticated", False) else None,
            sort_order=next_position,
        )
        self._audit(
            "source_uploaded",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={
                "asset_public_id": str(version.asset.public_id),
                "asset_version_public_id": str(version.public_id),
            },
        )
        return source_asset, version

    @transaction.atomic
    def add_occurrence(self, *, sheet, asset_version_public_id, actor, source="client_portal"):
        return self.add_occurrences(
            sheet=sheet,
            asset_version_public_id=asset_version_public_id,
            quantity=1,
            actor=actor,
            source=source,
        )[0]

    @transaction.atomic
    def add_occurrences(
        self,
        *,
        sheet,
        asset_version_public_id,
        quantity,
        actor,
        auto_place=False,
        source="client_portal",
    ):
        locked = self._lock_editable(sheet)
        version = self._resolve_available_version(locked, asset_version_public_id)
        quantity = self._bounded_positive_int(quantity, label="quantité")
        width, height = self._default_dimensions(locked, version)
        first_z_index = locked.items.count() + 1
        items = GangSheetItem.objects.bulk_create(
            [
                GangSheetItem(
                    customer=locked.customer,
                    sheet=locked,
                    asset_version=version,
                    x_mm=locked.margin_mm,
                    y_mm=locked.margin_mm,
                    width_mm=width,
                    height_mm=height,
                    z_index=first_z_index + offset,
                )
                for offset in range(quantity)
            ]
        )
        all_items = list(locked.items.all())
        if auto_place:
            changed = self.geometry.auto_place(sheet=locked, items=all_items)
            GangSheetItem.objects.bulk_update(changed, ["x_mm", "y_mm", "rotation", "updated_at"])
        self._refresh_sheet(locked)
        issues = self.geometry.issues(sheet=locked, items=all_items)
        if auto_place and issues:
            raise GangSheetDomainError(
                "AUTO_PLACE_FAILED",
                "La quantité demandée ne tient pas sur la hauteur maximale de la planche.",
                {"issues": issues},
            )
        self._mark_dirty(locked)
        self._audit(
            "item_added",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={
                "item_public_ids": [str(item.public_id) for item in items],
                "asset_public_id": str(version.asset.public_id),
                "quantity": quantity,
                "auto_placed": auto_place,
            },
        )
        return items

    @transaction.atomic
    def repeat_occurrence_grid(
        self,
        *,
        sheet,
        item_public_id,
        rows,
        columns,
        spacing_x_mm,
        spacing_y_mm,
        actor,
        source="client_portal",
    ):
        locked = self._lock_editable(sheet)
        source_item = (
            locked.items.select_related("asset_version").filter(public_id=item_public_id).first()
        )
        if source_item is None:
            raise GangSheetDomainError("ITEM_NOT_FOUND", "Occurrence introuvable.")
        rows = self._bounded_positive_int(rows, label="quantité de rangées")
        columns = self._bounded_positive_int(columns, label="quantité de colonnes")
        total = rows * columns
        if total < 2:
            raise GangSheetDomainError(
                "GRID_SIZE_REQUIRED", "Choisissez au moins deux exemplaires pour créer une grille."
            )
        if total > MAX_BATCH_OCCURRENCES:
            raise GangSheetDomainError(
                "BATCH_LIMIT_EXCEEDED",
                f"Une grille est limitée à {MAX_BATCH_OCCURRENCES} exemplaires.",
            )
        try:
            spacing_x = self._decimal(spacing_x_mm, allow_zero=True)
            spacing_y = self._decimal(spacing_y_mm, allow_zero=True)
        except (InvalidOperation, TypeError, ValueError) as error:
            raise GangSheetDomainError("INVALID_GRID", "Les espacements sont invalides.") from error

        effective_width = Decimal(source_item.effective_width_mm)
        effective_height = Decimal(source_item.effective_height_mm)
        origin_x = Decimal(source_item.x_mm)
        origin_y = Decimal(source_item.y_mm)
        final_right = origin_x + columns * effective_width + (columns - 1) * spacing_x
        final_bottom = origin_y + rows * effective_height + (rows - 1) * spacing_y
        if final_right > Decimal(locked.width_mm) or final_bottom > Decimal(
            locked.maximum_height_mm
        ):
            raise GangSheetDomainError(
                "GRID_TOO_LARGE",
                "Cette grille dépasse la laize ou la hauteur maximale de la planche.",
            )

        source_item.x_mm = origin_x
        source_item.y_mm = origin_y
        source_item.save(update_fields=["x_mm", "y_mm", "updated_at"])
        first_z_index = locked.items.count() + 1
        clones = []
        clone_offset = 0
        for row in range(rows):
            for column in range(columns):
                if row == 0 and column == 0:
                    continue
                clones.append(
                    GangSheetItem(
                        customer=locked.customer,
                        sheet=locked,
                        asset_version=source_item.asset_version,
                        x_mm=origin_x + column * (effective_width + spacing_x),
                        y_mm=origin_y + row * (effective_height + spacing_y),
                        width_mm=source_item.width_mm,
                        height_mm=source_item.height_mm,
                        rotation=source_item.rotation,
                        z_index=first_z_index + clone_offset,
                    )
                )
                clone_offset += 1
        GangSheetItem.objects.bulk_create(clones)
        all_items = list(locked.items.all())
        self._refresh_sheet(locked)
        issues = self.geometry.issues(sheet=locked, items=all_items)
        if issues:
            raise GangSheetDomainError(
                "GRID_CONFLICT",
                (
                    "La grille chevauche un autre visuel. "
                    "Libérez la zone ou utilisez le placement auto."
                ),
                {"issues": issues},
            )
        self._mark_dirty(locked)
        self._audit(
            "grid_created",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={
                "source_item_public_id": str(source_item.public_id),
                "rows": rows,
                "columns": columns,
                "quantity": total,
                "spacing_x_mm": str(spacing_x),
                "spacing_y_mm": str(spacing_y),
            },
        )
        return [source_item, *clones]

    @transaction.atomic
    def duplicate_occurrence(self, *, sheet, item_public_id, actor, source="client_portal"):
        locked = self._lock_editable(sheet)
        source_item = locked.items.filter(public_id=item_public_id).first()
        if source_item is None:
            raise GangSheetDomainError("ITEM_NOT_FOUND", "Occurrence introuvable.")
        item = GangSheetItem.objects.create(
            customer=locked.customer,
            sheet=locked,
            asset_version=source_item.asset_version,
            x_mm=source_item.x_mm + locked.item_spacing_mm,
            y_mm=source_item.y_mm + locked.item_spacing_mm,
            width_mm=source_item.width_mm,
            height_mm=source_item.height_mm,
            rotation=source_item.rotation,
            z_index=locked.items.count() + 1,
        )
        self._mark_dirty(locked)
        self._refresh_sheet(locked)
        self._audit("item_duplicated", sheet=locked, actor=actor, source=source)
        return item

    @transaction.atomic
    def delete_occurrence(self, *, sheet, item_public_id, actor, source="client_portal"):
        locked = self._lock_editable(sheet)
        item = locked.items.filter(public_id=item_public_id).first()
        if item is None:
            raise GangSheetDomainError("ITEM_NOT_FOUND", "Occurrence introuvable.")
        deleted_id = str(item.public_id)
        item.delete()
        self._normalize_z_indexes(locked)
        self._mark_dirty(locked)
        self._refresh_sheet(locked)
        self._audit(
            "item_deleted",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={"item_public_id": deleted_id},
        )

    @transaction.atomic
    def remove_source_asset(
        self,
        *,
        sheet,
        source_asset_public_id,
        actor,
        source="client_portal",
    ) -> str:
        locked = self._lock_editable(sheet)
        source_asset = (
            locked.source_assets.select_for_update()
            .select_related("asset")
            .filter(
                customer=locked.customer,
                public_id=source_asset_public_id,
            )
            .first()
        )
        if source_asset is None:
            raise GangSheetDomainError(
                "SOURCE_ASSET_NOT_FOUND",
                "Ce visuel n’est pas présent dans cette galerie.",
            )
        usage_count = locked.items.filter(asset_version__asset_id=source_asset.asset_id).count()
        if usage_count:
            raise GangSheetDomainError(
                "SOURCE_ASSET_IN_USE",
                (
                    "Ce visuel est encore utilisé sur la planche. Supprimez d’abord "
                    "ses occurrences de la composition."
                ),
                {"usage_count": usage_count},
            )

        asset_name = source_asset.asset.name
        asset_public_id = str(source_asset.asset.public_id)
        source_asset_public_id = str(source_asset.public_id)
        source_asset.delete()
        locked.save(update_fields=["updated_at"])
        self._audit(
            "source_removed",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={
                "asset_public_id": asset_public_id,
                "source_asset_public_id": source_asset_public_id,
                "asset_name": asset_name,
                "source_file_preserved": True,
            },
        )
        return asset_name

    @transaction.atomic
    def delete_sheet(self, *, sheet, actor, source="client_portal") -> None:
        locked = GangSheet.objects.select_for_update().get(pk=sheet.pk)
        if not self.can_client_delete(locked):
            if locked.status == GangSheet.Status.RENDERING:
                message = "Attendez la fin du rendu avant de supprimer cette planche."
            else:
                message = (
                    "Pour garantir la traçabilité, cette planche ne peut être supprimée "
                    "qu’avant son rattachement métier ou après sa transformation complète "
                    "en commande."
                )
            raise GangSheetDomainError(
                "SHEET_NOT_DELETABLE",
                message,
                {"current_status": locked.status},
            )

        stored_files = [
            (field.storage, field.name)
            for field in (locked.preview_file, locked.final_file)
            if field.name
        ]
        self._audit(
            "deleted",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={
                "name": locked.name,
                "status": locked.status,
                "item_count": locked.items.count(),
                "source_asset_count": locked.source_assets.count(),
                "order_public_id": str(locked.order.public_id) if locked.order_id else None,
                "production_asset_public_id": (
                    str(locked.production_asset.public_id) if locked.production_asset_id else None
                ),
                "project_preserved": bool(locked.project_id),
                "order_preserved": bool(locked.order_id),
                "production_asset_preserved": bool(locked.production_asset_id),
            },
        )
        locked.delete()
        transaction.on_commit(lambda: self._delete_stored_files(stored_files))

    @transaction.atomic
    def save_layout(
        self, *, sheet, payload: list[dict], expected_revision, actor, source="client_portal"
    ):
        locked = self._lock_editable(sheet)
        if expected_revision is not None and int(expected_revision) != locked.revision:
            raise GangSheetDomainError(
                "STALE_REVISION",
                "Ce brouillon a été modifié ailleurs. Rechargez la page avant de continuer.",
                {"revision": locked.revision},
            )
        items = {str(item.public_id): item for item in locked.items.select_for_update()}
        if set(items) != {str(row.get("public_id", "")) for row in payload}:
            raise GangSheetDomainError("INVALID_LAYOUT", "La liste des occurrences est incomplète.")
        try:
            for row in payload:
                item = items[str(row["public_id"])]
                item.x_mm = self._decimal(row.get("x_mm"), allow_zero=True)
                item.y_mm = self._decimal(row.get("y_mm"), allow_zero=True)
                item.width_mm = self._decimal(row.get("width_mm"))
                item.height_mm = self._decimal(row.get("height_mm"))
                item.rotation = normalize_rotation(row.get("rotation", 0))
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise GangSheetDomainError(
                "INVALID_LAYOUT", str(error) or "Placement invalide."
            ) from error
        GangSheetItem.objects.bulk_update(
            items.values(), ["x_mm", "y_mm", "width_mm", "height_mm", "rotation", "updated_at"]
        )
        self._mark_dirty(locked)
        self._refresh_sheet(locked)
        issues = self.geometry.issues(sheet=locked, items=list(items.values()))
        self._audit(
            "draft_saved",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={"issues": len(issues)},
        )
        return locked, issues

    @transaction.atomic
    def auto_place(self, *, sheet, actor, source="client_portal"):
        locked = self._lock_editable(sheet)
        items = list(locked.items.select_for_update())
        if not items:
            raise GangSheetDomainError("ITEMS_REQUIRED", "Ajoutez au moins un visuel.")
        changed = self.geometry.auto_place(sheet=locked, items=items)
        GangSheetItem.objects.bulk_update(changed, ["x_mm", "y_mm", "rotation", "updated_at"])
        self._mark_dirty(locked)
        self._refresh_sheet(locked)
        issues = self.geometry.issues(sheet=locked, items=items)
        if issues:
            raise GangSheetDomainError(
                "AUTO_PLACE_FAILED",
                "La planche est trop petite pour placer toutes les occurrences.",
                {"issues": issues},
            )
        self._audit("auto_placed", sheet=locked, actor=actor, source=source)
        return locked

    @transaction.atomic
    def request_render(self, *, sheet, actor, source="client_portal"):
        locked = self._lock_editable(sheet)
        items = list(locked.items.select_for_update().select_related("asset_version"))
        issues = self.geometry.issues(sheet=locked, items=items)
        if not items:
            raise GangSheetDomainError("ITEMS_REQUIRED", "Ajoutez au moins un visuel.")
        if issues:
            raise GangSheetDomainError(
                "INVALID_GEOMETRY",
                "Corrigez les débordements et chevauchements avant le rendu.",
                {"issues": issues},
            )
        locked.status = GangSheet.Status.RENDERING
        locked.render_error = ""
        locked.render_requested_at = timezone.now()
        locked.save(update_fields=["status", "render_error", "render_requested_at", "updated_at"])
        from apps.gang_sheets.tasks import render_gang_sheet_task

        transaction.on_commit(lambda: render_gang_sheet_task.delay(str(locked.public_id)))
        self._audit("render_requested", sheet=locked, actor=actor, source=source)
        return locked

    @transaction.atomic
    def validate_sheet(self, *, sheet, actor, source="client_portal"):
        locked = GangSheet.objects.select_for_update().get(pk=sheet.pk)
        if locked.status != GangSheet.Status.READY or not locked.final_file:
            raise GangSheetDomainError(
                "RENDER_REQUIRED", "Le rendu final doit être terminé avant validation."
            )
        items = list(locked.items.all())
        issues = self.geometry.issues(sheet=locked, items=items)
        if issues:
            raise GangSheetDomainError(
                "INVALID_GEOMETRY", "La géométrie de la planche est invalide."
            )
        locked.status = GangSheet.Status.VALIDATED
        locked.validated_at = timezone.now()
        locked.validated_by = actor if getattr(actor, "is_authenticated", False) else None
        locked.order = locked.project.converted_order if locked.project_id else None
        locked.save(update_fields=["status", "validated_at", "validated_by", "order", "updated_at"])
        transaction.on_commit(
            lambda: self.drive_sync.schedule_sync(
                sheet=locked,
                actor=actor,
                source=f"{source}.validation",
            )
        )
        self._audit(
            "validated",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={"order_public_id": str(locked.order.public_id) if locked.order else None},
        )
        return locked

    @transaction.atomic
    def create_order_project(self, *, sheet, actor, source="client_portal"):
        """Transforme une planche validée en un projet contenant uniquement son PDF final."""
        locked = GangSheet.objects.select_for_update().get(pk=sheet.pk)
        if locked.status != GangSheet.Status.VALIDATED or not locked.final_file:
            raise GangSheetDomainError(
                "VALIDATED_SHEET_REQUIRED",
                "Validez la planche avant de préparer la commande.",
            )
        transaction.on_commit(
            lambda: self.drive_sync.schedule_sync(
                sheet=locked,
                actor=actor,
                source=f"{source}.order_project",
            )
        )
        if locked.project_id:
            return locked.project

        project = self.projects.create_project(
            customer=locked.customer,
            actor=actor,
            data={
                "name": locked.name,
                "order_mode": B2BOrderProject.OrderMode.READY_GANG_SHEET,
                "customer_comment": (
                    "Projet généré automatiquement depuis une Gang Sheet validée."
                ),
            },
            source=source,
        )
        item = self.projects.add_item(
            project=project,
            actor=actor,
            data={
                "name": f"{locked.name} — planche finale",
                "width_mm": locked.width_mm,
                "height_mm": locked.height_mm,
                "quantity": 1,
                "rotation_allowed": False,
                "individual_cutting": False,
            },
            source=source,
        )
        locked.final_file.open("rb")
        final_upload = File(
            locked.final_file.file,
            name=f"{locked.public_id}-production.pdf",
        )
        final_upload.content_type = "application/pdf"
        try:
            version = self.assets.create_production_asset(
                customer=locked.customer,
                actor=actor,
                name=f"{locked.name} — fichier production",
                uploaded_file=final_upload,
                source=source,
                metadata={
                    "gang_sheet_public_id": str(locked.public_id),
                },
            )
        except AssetDomainError as error:
            raise GangSheetDomainError(error.code, error.message, error.details) from error
        finally:
            locked.final_file.close()

        item.asset = version.asset
        item.save(update_fields=["asset", "updated_at"])
        self.projects.refresh_completeness(project=project)
        locked.project = project
        locked.production_asset = version.asset
        locked.save(update_fields=["project", "production_asset", "updated_at"])
        self._audit(
            "order_project_created",
            sheet=locked,
            actor=actor,
            source=source,
            metadata={
                "project_public_id": str(project.public_id),
                "asset_public_id": str(version.asset.public_id),
            },
        )
        return self.projects.get_customer_project(
            customer=locked.customer,
            project_public_id=project.public_id,
        )

    @transaction.atomic
    def attach_validated_sheets_to_order(self, *, project, order, actor, source):
        sheets = list(
            GangSheet.objects.select_for_update()
            .for_project(project)
            .filter(status=GangSheet.Status.VALIDATED, order__isnull=True)
        )
        for sheet in sheets:
            sheet.order = order
        GangSheet.objects.bulk_update(sheets, ["order", "updated_at"])
        for sheet in sheets:
            self._audit(
                "attached_to_order",
                sheet=sheet,
                actor=actor,
                source=source,
                metadata={"order_public_id": str(order.public_id)},
            )
        return sheets

    def serialize_sheet(self, sheet, *, preview_url_resolver) -> dict:
        items = list(sheet.items.select_related("asset_version__asset"))
        issues = self.geometry.issues(sheet=sheet, items=items)
        issue_ids = {item_id for issue in issues for item_id in issue["item_public_ids"]}
        return {
            "public_id": str(sheet.public_id),
            "name": sheet.name,
            "status": sheet.status,
            "revision": sheet.revision,
            "width_mm": float(sheet.width_mm),
            "height_mm": float(sheet.height_mm),
            "minimum_height_mm": float(sheet.minimum_height_mm),
            "maximum_height_mm": float(sheet.maximum_height_mm),
            "height_step_mm": float(sheet.height_step_mm),
            "margin_mm": float(sheet.margin_mm),
            "spacing_mm": float(sheet.item_spacing_mm),
            "surface_sqm": float(sheet.surface_sqm),
            "unit_price_eur": float(sheet.unit_price_eur),
            "estimated_price_eur": float(sheet.estimated_price_eur),
            "issues": issues,
            "items": [
                {
                    "public_id": str(item.public_id),
                    "asset_name": item.asset_version.asset.name,
                    "asset_version_public_id": str(item.asset_version.public_id),
                    "preview_url": preview_url_resolver(item.asset_version),
                    "x_mm": float(item.x_mm),
                    "y_mm": float(item.y_mm),
                    "width_mm": float(item.width_mm),
                    "height_mm": float(item.height_mm),
                    "rotation": item.rotation,
                    "has_issue": str(item.public_id) in issue_ids,
                }
                for item in items
            ],
        }

    def _lock_editable(self, sheet):
        locked = GangSheet.objects.select_for_update().get(pk=sheet.pk)
        if locked.status not in self.editable_statuses:
            raise GangSheetDomainError("SHEET_LOCKED", "Cette planche n'est plus modifiable.")
        return locked

    def _resolve_available_version(self, sheet, public_id):
        version = self.available_asset_versions(sheet=sheet).filter(public_id=public_id).first()
        if version is None:
            raise GangSheetDomainError(
                "ASSET_NOT_AVAILABLE",
                "Ce fichier n'est pas rattaché ou pas encore prêt dans cette galerie.",
            )
        return version

    def _default_dimensions(self, sheet, version):
        source_asset = (
            sheet.source_assets.filter(customer=sheet.customer, asset=version.asset)
            .order_by("sort_order")
            .first()
        )
        if source_asset is not None and source_asset.width_mm and source_asset.height_mm:
            return source_asset.width_mm, source_asset.height_mm
        analysis = getattr(version, "analysis", None)
        if (
            analysis
            and analysis.image_width
            and analysis.image_height
            and analysis.dpi_x
            and analysis.dpi_y
        ):
            return (
                (Decimal(analysis.image_width) / analysis.dpi_x * Decimal("25.4")).quantize(
                    HUNDREDTH
                ),
                (Decimal(analysis.image_height) / analysis.dpi_y * Decimal("25.4")).quantize(
                    HUNDREDTH
                ),
            )
        raise GangSheetDomainError(
            "DIMENSIONS_REQUIRED", "La taille physique du fichier est inconnue."
        )

    def _refresh_sheet(self, sheet):
        items = list(sheet.items.all())
        sheet.height_mm = self.geometry.required_height(sheet=sheet, items=items)
        self._refresh_totals(sheet, items)

    def _refresh_totals(self, sheet, _items):
        sheet.surface_sqm = (
            Decimal(sheet.width_mm) * Decimal(sheet.height_mm) / Decimal("1000000")
        ).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        sheet.estimated_price_eur = (sheet.surface_sqm * Decimal(sheet.unit_price_eur)).quantize(
            HUNDREDTH, rounding=ROUND_HALF_UP
        )
        sheet.save(update_fields=["height_mm", "surface_sqm", "estimated_price_eur", "updated_at"])

    def _mark_dirty(self, sheet):
        sheet.revision += 1
        sheet.status = GangSheet.Status.DRAFT
        sheet.render_error = ""
        if sheet.preview_file:
            sheet.preview_file.delete(save=False)
            sheet.preview_file = ""
        if sheet.final_file:
            sheet.final_file.delete(save=False)
            sheet.final_file = ""
        sheet.rendered_at = None
        sheet.save(
            update_fields=[
                "revision",
                "status",
                "render_error",
                "preview_file",
                "final_file",
                "rendered_at",
                "updated_at",
            ]
        )

    @staticmethod
    def _normalize_z_indexes(sheet):
        items = list(sheet.items.order_by("z_index", "created_at"))
        for index, item in enumerate(items, start=1):
            item.z_index = index + 100000
        GangSheetItem.objects.bulk_update(items, ["z_index"])
        for index, item in enumerate(items, start=1):
            item.z_index = index
        GangSheetItem.objects.bulk_update(items, ["z_index"])

    @staticmethod
    def _delete_stored_files(stored_files):
        for storage, name in stored_files:
            storage.delete(name)

    def _unit_price(self, customer):
        try:
            return self.pricing.resolve_unit_price_per_sqm(customer=customer)
        except ValidationError as error:
            raise GangSheetDomainError("PRICING_UNAVAILABLE", "; ".join(error.messages)) from error

    @staticmethod
    def _decimal(value, *, allow_zero=False):
        number = Decimal(str(value)).quantize(HUNDREDTH)
        if number < 0 or (number == 0 and not allow_zero):
            raise ValueError("Les dimensions doivent être strictement positives.")
        return number

    @staticmethod
    def _bounded_positive_int(value, *, label):
        try:
            number = int(value)
        except (TypeError, ValueError) as error:
            raise GangSheetDomainError("INVALID_QUANTITY", f"La {label} est invalide.") from error
        if number < 1:
            raise GangSheetDomainError(
                "INVALID_QUANTITY", f"La {label} doit être supérieure ou égale à 1."
            )
        if number > MAX_BATCH_OCCURRENCES:
            raise GangSheetDomainError(
                "BATCH_LIMIT_EXCEEDED",
                f"La {label} est limitée à {MAX_BATCH_OCCURRENCES}.",
            )
        return number

    @staticmethod
    def _audit(action, *, sheet, actor, source, metadata=None):
        record_event(
            action=f"gang_sheet.{action}",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=sheet,
            metadata={
                "customer_public_id": str(sheet.customer.public_id),
                "project_public_id": str(sheet.project.public_id) if sheet.project_id else None,
                "source": source,
                **(metadata or {}),
            },
        )


# Import local pour conserver les annotations/queries lisibles sans masquer models.Model.
from django.db import models  # noqa: E402
