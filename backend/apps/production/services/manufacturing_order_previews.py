from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageOps


class ManufacturingOrderPreviewService:
    """Prépare des aperçus légers, intégrables dans un document interne Atelier."""

    max_side_px = 420

    def build_for_order(self, *, order) -> dict[str, bytes]:
        previews: dict[str, bytes] = {}
        for order_upload in order.uploads.all().order_by("sort_order", "created_at"):
            preview = self._build_upload_preview(order_upload=order_upload)
            if preview is not None:
                previews[str(order_upload.public_id)] = preview
        return previews

    def _build_upload_preview(self, *, order_upload) -> bytes | None:
        from apps.uploads.services.asset_preview import AssetPreviewRenderer

        source = getattr(order_upload, "asset_version", None) or order_upload
        analysis = getattr(source, "analysis", None)
        if analysis is not None and analysis.thumbnail:
            source = self._thumbnail_source(file=analysis.thumbnail)

        try:
            rendered = AssetPreviewRenderer().render(version=source)
            image = ImageOps.exif_transpose(rendered.image)
            image.thumbnail(
                (self.max_side_px, self.max_side_px),
                Image.Resampling.LANCZOS,
            )
            canvas = Image.new("RGB", image.size, "white")
            if image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            ):
                alpha_image = image.convert("RGBA")
                canvas.paste(alpha_image, mask=alpha_image.getchannel("A"))
            else:
                canvas.paste(image.convert("RGB"))

            output = BytesIO()
            canvas.save(output, format="PNG", optimize=True)
            return output.getvalue()
        except Exception:
            return None
        finally:
            try:
                rendered.image.close()
            except (NameError, AttributeError):
                pass

    def _thumbnail_source(self, *, file):
        return SimpleNamespace(
            file=file,
            original_filename="atelier-preview.webp",
            mime_type="image/webp",
        )
