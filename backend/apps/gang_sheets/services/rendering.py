from __future__ import annotations

from io import BytesIO

import pymupdf
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image

from apps.gang_sheets.models import GangSheet
from apps.gang_sheets.services.drive import GangSheetDriveSyncService
from apps.gang_sheets.services.geometry import GangSheetGeometryService
from apps.gang_sheets.services.hybrid_pdf import GangSheetHybridPdfComposer
from apps.uploads.services.asset_preview import AssetPreviewError, AssetPreviewRenderer


class GangSheetRenderError(RuntimeError):
    pass


class GangSheetRenderService:
    preview_width_px = 1200

    def __init__(
        self,
        *,
        geometry=None,
        preview_renderer=None,
        drive_sync=None,
        production_composer=None,
    ):
        self.geometry = geometry or GangSheetGeometryService()
        self.preview_renderer = preview_renderer or AssetPreviewRenderer()
        self.drive_sync = drive_sync or GangSheetDriveSyncService()
        self.production_composer = production_composer or GangSheetHybridPdfComposer(
            preview_renderer=self.preview_renderer
        )

    def render(self, *, sheet_public_id):
        sheet = (
            GangSheet.objects.select_related("customer", "project")
            .prefetch_related("items__asset_version__asset")
            .filter(public_id=sheet_public_id)
            .first()
        )
        if sheet is None:
            raise GangSheetRenderError("Planche introuvable.")
        if sheet.status != GangSheet.Status.RENDERING:
            return sheet
        items = list(sheet.items.select_related("asset_version__asset"))
        issues = self.geometry.issues(sheet=sheet, items=items)
        if not items or issues:
            return self._fail(sheet, "La géométrie a changé avant le rendu.")
        try:
            preview = self._render_preview(sheet, items)
            production_pdf = self._render_production_pdf(sheet, items)
        except (AssetPreviewError, OSError, ValueError, RuntimeError) as error:
            return self._fail(sheet, str(error)[:255] or "Rendu impossible.")

        with transaction.atomic():
            locked = GangSheet.objects.select_for_update().get(pk=sheet.pk)
            if locked.status != GangSheet.Status.RENDERING or locked.revision != sheet.revision:
                return locked
            locked.preview_file.save(
                f"preview-r{locked.revision}.png", ContentFile(preview), save=False
            )
            locked.final_file.save(
                f"production-r{locked.revision}.pdf", ContentFile(production_pdf), save=False
            )
            locked.status = GangSheet.Status.READY
            locked.rendered_at = timezone.now()
            locked.render_error = ""
            locked.save(
                update_fields=[
                    "preview_file",
                    "final_file",
                    "status",
                    "rendered_at",
                    "render_error",
                    "updated_at",
                ]
            )
            transaction.on_commit(
                lambda: self.drive_sync.schedule_sync(
                    sheet=locked,
                    source="gang_sheet.render",
                )
            )
            return locked

    def _render_preview(self, sheet, items) -> bytes:
        scale = self.preview_width_px / float(sheet.width_mm)
        height_px = max(1, round(float(sheet.height_mm) * scale))
        if height_px > 6000:
            scale = 6000 / float(sheet.height_mm)
            width_px = max(1, round(float(sheet.width_mm) * scale))
            height_px = 6000
        else:
            width_px = self.preview_width_px
        canvas = Image.new("RGBA", (width_px, height_px), (255, 255, 255, 0))
        for item in items:
            target_width = max(1, round(float(item.width_mm) * scale))
            target_height = max(1, round(float(item.height_mm) * scale))
            image = self._source_image(
                item.asset_version, target_width=target_width, target_height=target_height
            )
            image = image.resize((target_width, target_height), Image.Resampling.LANCZOS)
            image = self._rotate(image, item.rotation)
            x = round(float(item.x_mm) * scale)
            y = round(float(item.y_mm) * scale)
            canvas.alpha_composite(image, (x, y))
            image.close()
        output = BytesIO()
        canvas.save(output, format="PNG", optimize=True, dpi=(96, 96))
        canvas.close()
        return output.getvalue()

    def _render_production_pdf(self, sheet, items) -> bytes:
        return self.production_composer.compose(sheet=sheet, items=items)

    def _source_image(self, version, *, target_width: int, target_height: int) -> Image.Image:
        content = self._read_version(version)
        if version.mime_type == "application/pdf" or content.startswith(b"%PDF-"):
            try:
                with pymupdf.open(stream=content, filetype="pdf") as document:
                    page = document.load_page(0)
                    zoom = max(
                        target_width / max(page.rect.width, 1),
                        target_height / max(page.rect.height, 1),
                    )
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(zoom, zoom),
                        colorspace=pymupdf.csRGB,
                        alpha=True,
                        annots=False,
                    )
                    return Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)
            except (RuntimeError, ValueError) as error:
                raise GangSheetRenderError("Le PDF source ne peut pas être rendu.") from error
        rendered = self.preview_renderer.render(version=version)
        image = rendered.image
        if image.mode != "RGBA":
            converted = image.convert("RGBA")
            image.close()
            image = converted
        return image

    @staticmethod
    def _read_version(version) -> bytes:
        version.file.open("rb")
        try:
            return version.file.read()
        finally:
            version.file.close()

    @staticmethod
    def _rotate(image: Image.Image, rotation: int) -> Image.Image:
        if rotation == 0:
            return image
        rotated = image.rotate(-rotation, expand=True, resample=Image.Resampling.BICUBIC)
        image.close()
        return rotated

    @staticmethod
    def _fail(sheet, message: str):
        with transaction.atomic():
            locked = GangSheet.objects.select_for_update().get(pk=sheet.pk)
            if locked.status == GangSheet.Status.RENDERING:
                locked.status = GangSheet.Status.RENDER_FAILED
                locked.render_error = message[:255]
                locked.save(update_fields=["status", "render_error", "updated_at"])
            return locked
