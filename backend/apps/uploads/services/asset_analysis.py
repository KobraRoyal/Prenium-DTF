from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone
from PIL import ImageStat, UnidentifiedImageError

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.uploads.models import AssetAnalysis, AssetVersion
from apps.uploads.services.asset_preview import AssetPreviewRenderer
from apps.uploads.services.asset_semi_transparency import AssetSemiTransparencyAnalyzer
from apps.uploads.services.asset_thin_zones import AssetThinZoneAnalyzer


class AssetAnalysisService:
    def __init__(self):
        self.preview_renderer = AssetPreviewRenderer()
        self.thin_zone_analyzer = AssetThinZoneAnalyzer()
        self.semi_transparency_analyzer = AssetSemiTransparencyAnalyzer()

    def analyze(self, *, version_public_id, source: str = "celery") -> AssetVersion | None:
        version = (
            AssetVersion.objects.select_related("asset", "customer")
            .filter(public_id=version_public_id)
            .first()
        )
        if version is None:
            return None
        AssetVersion.objects.filter(pk=version.pk).update(
            analysis_status=AssetVersion.AnalysisStatus.PROCESSING,
            analysis_error="",
        )
        try:
            result = self._analyze_file(version)
        except (OSError, UnidentifiedImageError, ValueError) as error:
            AssetVersion.objects.filter(pk=version.pk).update(
                analysis_status=AssetVersion.AnalysisStatus.FAILED,
                analysis_error=str(error)[:255],
            )
            record_event(
                action="asset.analysis_failed",
                target=version.asset,
                status=AuditLogEntry.Status.FAILURE,
                message=str(error)[:255],
                metadata=self._metadata(version, source),
            )
            self._refresh_projects(version.asset)
            return AssetVersion.objects.get(pk=version.pk)

        try:
            with transaction.atomic():
                auto_size = self._apply_auto_size(version=version, result=result)
                analysis, _created = AssetAnalysis.objects.update_or_create(
                    version=version,
                    defaults={
                        "customer": version.customer,
                        "image_width": result["image_width"],
                        "image_height": result["image_height"],
                        "dpi_x": result["dpi_x"],
                        "dpi_y": result["dpi_y"],
                        "has_alpha": result["has_alpha"],
                        "probable_white_background": result["probable_white_background"],
                        "warnings": result["warnings"],
                        "metadata": result["metadata"],
                        "analyzed_at": timezone.now(),
                    },
                )
                update_fields = ["updated_at"]
                if result["thumbnail"] is not None:
                    if analysis.thumbnail:
                        analysis.thumbnail.delete(save=False)
                    analysis.thumbnail.save(
                        f"{version.public_id}.webp",
                        ContentFile(result["thumbnail"]),
                        save=False,
                    )
                    update_fields.append("thumbnail")
                if analysis.thin_zone_overlay:
                    analysis.thin_zone_overlay.delete(save=False)
                if result["thin_zone_overlay"] is not None:
                    analysis.thin_zone_overlay.save(
                        f"{version.public_id}-thin-zones.webp",
                        ContentFile(result["thin_zone_overlay"]),
                        save=False,
                    )
                    update_fields.append("thin_zone_overlay")
                elif not analysis.thin_zone_overlay:
                    analysis.thin_zone_overlay = ""
                    update_fields.append("thin_zone_overlay")
                if analysis.semi_transparency_overlay:
                    analysis.semi_transparency_overlay.delete(save=False)
                if result["semi_transparency_overlay"] is not None:
                    analysis.semi_transparency_overlay.save(
                        f"{version.public_id}-semi-transparency.webp",
                        ContentFile(result["semi_transparency_overlay"]),
                        save=False,
                    )
                    update_fields.append("semi_transparency_overlay")
                elif not analysis.semi_transparency_overlay:
                    analysis.semi_transparency_overlay = ""
                    update_fields.append("semi_transparency_overlay")
                if len(update_fields) > 1:
                    analysis.save(update_fields=update_fields)
                status = (
                    AssetVersion.AnalysisStatus.WARNING
                    if result["warnings"]
                    or result["thin_zone"]["detected"]
                    or result["semi_transparency"]["detected"]
                    else AssetVersion.AnalysisStatus.READY
                )
                version.analysis_status = status
                version.analysis_error = ""
                version.auto_size_requested = False
                version.save(
                    update_fields=[
                        "analysis_status",
                        "analysis_error",
                        "auto_size_requested",
                        "updated_at",
                    ]
                )
        except IntegrityError as error:
            AssetVersion.objects.filter(pk=version.pk).update(
                analysis_status=AssetVersion.AnalysisStatus.FAILED,
                analysis_error="Erreur lors de l'enregistrement de l'analyse.",
            )
            record_event(
                action="asset.analysis_failed",
                target=version.asset,
                status=AuditLogEntry.Status.FAILURE,
                message=str(error)[:255],
                metadata=self._metadata(version, source),
            )
            self._refresh_projects(version.asset)
            return AssetVersion.objects.get(pk=version.pk)
        record_event(
            action="asset.analyzed",
            target=version.asset,
            metadata={
                **self._metadata(version, source),
                "analysis_status": version.analysis_status,
                "warnings": result["warnings"],
                "thin_zone": result["thin_zone"],
                "semi_transparency": result["semi_transparency"],
                "auto_size_mm": auto_size,
            },
        )
        self._refresh_projects(version.asset)
        return version

    def _refresh_projects(self, asset):
        from apps.b2b_order_projects.services import B2BOrderProjectService

        service = B2BOrderProjectService()
        for item in asset.b2b_order_project_items.select_related("project"):
            service.refresh_completeness(project=item.project)

    def _analyze_file(self, version):
        rendered = self.preview_renderer.render(version=version)
        image = rendered.image
        try:
            width = rendered.source_width
            height = rendered.source_height
            dpi_x = rendered.dpi_x
            dpi_y = rendered.dpi_y
            has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
            white_background = self._probable_white_background(image)
            thin_zone_result = self.thin_zone_analyzer.analyze(
                image=image,
                dpi_x=dpi_x,
                dpi_y=dpi_y,
                metadata=rendered.metadata,
                probable_white_background=white_background,
            )
            semi_transparency_result = self.semi_transparency_analyzer.analyze(image=image)
            warnings = list(rendered.warnings)
            if not has_alpha:
                warnings.append("Aucune transparence détectée.")
            if white_background:
                warnings.append("Fond blanc probable détecté.")
            if dpi_x is None or dpi_y is None:
                if rendered.metadata.get("dimension_basis") != "page":
                    warnings.append(
                        "DPI source absent : dimensions proposées sur une base de 300 DPI."
                    )
            thumbnail = self._thumbnail(image)
            return {
                "image_width": width,
                "image_height": height,
                "dpi_x": dpi_x,
                "dpi_y": dpi_y,
                "page_width_in": rendered.metadata.get("page_width_in"),
                "page_height_in": rendered.metadata.get("page_height_in"),
                "has_alpha": has_alpha,
                "probable_white_background": white_background,
                "warnings": warnings,
                "metadata": {
                    **rendered.metadata,
                    "mode": image.mode,
                    "format": rendered.format_name,
                    "mime_type": version.mime_type,
                    "thin_zone": thin_zone_result.metadata,
                    "semi_transparency": semi_transparency_result.metadata,
                },
                "thumbnail": thumbnail,
                "thin_zone": thin_zone_result.metadata,
                "thin_zone_overlay": thin_zone_result.overlay,
                "semi_transparency": semi_transparency_result.metadata,
                "semi_transparency_overlay": semi_transparency_result.overlay,
            }
        finally:
            image.close()

    def _apply_auto_size(self, *, version, result):
        if not version.auto_size_requested:
            return None

        millimeters_per_inch = Decimal("25.4")
        metadata = result.get("metadata") or {}
        page_width_in = result.get("page_width_in")
        page_height_in = result.get("page_height_in")
        if metadata.get("uses_artboard_dimensions") and metadata.get("artboard_width_mm"):
            width_mm = Decimal(str(metadata["artboard_width_mm"])).quantize(Decimal("0.01"))
            height_mm = Decimal(str(metadata["artboard_height_mm"])).quantize(Decimal("0.01"))
        elif result.get("dpi_x") and result.get("image_width") and result.get("image_height"):
            dpi_x = Decimal(str(result["dpi_x"]))
            dpi_y = Decimal(str(result["dpi_y"] or result["dpi_x"]))
            width_mm = (Decimal(result["image_width"]) * millimeters_per_inch / dpi_x).quantize(
                Decimal("0.01")
            )
            height_mm = (Decimal(result["image_height"]) * millimeters_per_inch / dpi_y).quantize(
                Decimal("0.01")
            )
        elif page_width_in and page_height_in:
            width_mm = (Decimal(str(page_width_in)) * millimeters_per_inch).quantize(
                Decimal("0.01")
            )
            height_mm = (Decimal(str(page_height_in)) * millimeters_per_inch).quantize(
                Decimal("0.01")
            )
        elif result.get("image_width") and result.get("image_height"):
            dpi_x = Decimal("300")
            dpi_y = Decimal("300")
            width_mm = (Decimal(result["image_width"]) * millimeters_per_inch / dpi_x).quantize(
                Decimal("0.01")
            )
            height_mm = (Decimal(result["image_height"]) * millimeters_per_inch / dpi_y).quantize(
                Decimal("0.01")
            )
        else:
            return None
        version.asset.b2b_order_project_items.filter(
            customer=version.customer,
            asset__current_version=version,
        ).update(width_mm=width_mm, height_mm=height_mm)
        return {"width": str(width_mm), "height": str(height_mm)}

    def _probable_white_background(self, image) -> bool:
        sample = image.convert("RGB")
        sample.thumbnail((48, 48))
        stats = ImageStat.Stat(sample)
        mean = stats.mean[:3]
        corners = [
            sample.getpixel((0, 0)),
            sample.getpixel((sample.width - 1, 0)),
            sample.getpixel((0, sample.height - 1)),
            sample.getpixel((sample.width - 1, sample.height - 1)),
        ]
        return min(mean) > 235 and all(min(pixel) > 235 for pixel in corners)

    def _thumbnail(self, image) -> bytes:
        preview = image.copy()
        try:
            preview.thumbnail((480, 480))
            normalized = preview.convert("RGBA" if self._has_alpha(preview) else "RGB")
            try:
                output = BytesIO()
                normalized.save(output, format="WEBP", quality=82, method=4)
                return output.getvalue()
            finally:
                normalized.close()
        finally:
            preview.close()

    def _has_alpha(self, image) -> bool:
        return image.mode in {"RGBA", "LA"} or "transparency" in image.info

    def _metadata(self, version, source):
        return {
            "customer_public_id": str(version.customer.public_id),
            "asset_public_id": str(version.asset.public_id),
            "asset_version_public_id": str(version.public_id),
            "source": source,
        }
