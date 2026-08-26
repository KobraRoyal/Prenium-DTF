from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import pymupdf
from PIL import Image, ImageChops, ImageFilter


@dataclass(frozen=True)
class SemiTransparencyAnalysisResult:
    detected: bool
    overlay: bytes | None
    metadata: dict[str, object]


class AssetSemiTransparencyAnalyzer:
    """Detect partial alpha values that are unreliable in DTF printing."""

    min_alpha = 16
    max_alpha = 250
    min_pixels = 48
    min_coverage_percent = 0.02
    max_overlay_side = 480
    overlay_rgb = (255, 152, 0)
    # Soft-mask fringe (PNG AA) — ignore near-opaque alphas that are not real fades.
    embedded_soft_mask_max_alpha = 220
    embedded_soft_mask_erode = 3
    overlay_dilate = 1
    render_antialias_filter = 3

    def analyze(
        self,
        *,
        image: Image.Image,
        source_is_pure_vector: bool = False,
        source_has_opacity: bool = False,
        erode_render_antialias: bool = False,
    ) -> SemiTransparencyAnalysisResult:
        if source_is_pure_vector and not source_has_opacity:
            return self._empty_result(skip_reason="pure_vector_source")

        alpha_channel_present = self._has_native_alpha(image)
        rgba = image.convert("RGBA")
        try:
            alpha = rgba.getchannel("A")
            try:
                result = self._analyze_alpha_channel(
                    alpha,
                    erode_render_antialias=erode_render_antialias,
                    alpha_channel_present=alpha_channel_present,
                )
            finally:
                alpha.close()
        finally:
            rgba.close()
        return result

    def analyze_pdf_document(
        self,
        *,
        content: bytes,
        preview_image: Image.Image,
        page_width_points: float | None,
        page_height_points: float | None,
        is_pure_vector: bool,
        has_source_opacity: bool,
    ) -> SemiTransparencyAnalysisResult:
        """Analyse PDF : alphas natifs des images + opacité vectorielle sans AA de rendu."""
        if is_pure_vector and not has_source_opacity:
            return self._empty_result(skip_reason="pure_vector_source")

        preview_size = preview_image.size
        page_mask = Image.new("L", preview_size, 0)
        try:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                if document.page_count < 1:
                    return self._empty_result()
                page = document.load_page(0)
                zoom_x, zoom_y = self._preview_zoom(
                    preview_size=preview_size,
                    page_width_points=page_width_points,
                    page_height_points=page_height_points,
                    page=page,
                )
                self._accumulate_embedded_image_masks(
                    document=document,
                    page=page,
                    page_mask=page_mask,
                    zoom_x=zoom_x,
                    zoom_y=zoom_y,
                )
                if has_source_opacity:
                    self._accumulate_preview_opacity_mask(
                        preview_image=preview_image,
                        page_mask=page_mask,
                    )

            return self._result_from_mask(
                page_mask,
                alpha_channel_present=True,
                analysis_mode="pdf_embedded_and_opacity",
            )
        finally:
            page_mask.close()

    def _analyze_alpha_channel(
        self,
        alpha: Image.Image,
        *,
        erode_render_antialias: bool,
        alpha_channel_present: bool,
    ) -> SemiTransparencyAnalysisResult:
        alpha_min, alpha_max = alpha.getextrema()
        if alpha_max < self.min_alpha or alpha_min >= 255:
            return self._empty_result(
                alpha_channel_present=alpha_channel_present,
            )

        semi_mask = alpha.point(
            lambda value: 255 if self.min_alpha <= value <= self.max_alpha else 0
        )
        try:
            if erode_render_antialias:
                eroded = semi_mask.filter(ImageFilter.MinFilter(self.render_antialias_filter))
                semi_mask.close()
                semi_mask = eroded
            return self._result_from_mask(
                semi_mask,
                alpha_channel_present=alpha_channel_present,
                analysis_mode=("render_eroded" if erode_render_antialias else "native_alpha"),
            )
        finally:
            semi_mask.close()

    def _result_from_mask(
        self,
        semi_mask: Image.Image,
        *,
        alpha_channel_present: bool,
        analysis_mode: str,
    ) -> SemiTransparencyAnalysisResult:
        semi_pixels = self._count_mask_pixels(semi_mask)
        total_pixels = max(semi_mask.width * semi_mask.height, 1)
        coverage_percent = round((semi_pixels / total_pixels) * 100, 4)
        detected = semi_pixels >= self.min_pixels and coverage_percent >= self.min_coverage_percent
        overlay = self._build_overlay(semi_mask) if detected else None
        return SemiTransparencyAnalysisResult(
            detected=detected,
            overlay=overlay,
            metadata={
                "detected": detected,
                "min_alpha": self.min_alpha,
                "max_alpha": self.max_alpha,
                "min_pixels": self.min_pixels,
                "min_coverage_percent": self.min_coverage_percent,
                "pixel_count": semi_pixels,
                "coverage_percent": coverage_percent,
                "alpha_channel_present": alpha_channel_present,
                "analysis_mode": analysis_mode,
                "skipped": False,
                "skip_reason": None,
            },
        )

    def _accumulate_embedded_image_masks(
        self,
        *,
        document: pymupdf.Document,
        page: pymupdf.Page,
        page_mask: Image.Image,
        zoom_x: float,
        zoom_y: float,
    ) -> None:
        images_by_xref = {item[0]: item for item in page.get_images(full=True)}
        for info in page.get_image_info(xrefs=True):
            xref = int(info.get("xref") or 0)
            if xref <= 0:
                continue
            bbox = info.get("bbox")
            if not bbox:
                continue
            image_meta = images_by_xref.get(xref)
            smask_xref = int(image_meta[1]) if image_meta else 0
            embedded = self._extract_embedded_rgba(
                document=document,
                xref=xref,
                smask_xref=smask_xref,
            )
            if embedded is None:
                continue
            try:
                alpha = embedded.getchannel("A")
                try:
                    alpha_min, alpha_max = alpha.getextrema()
                    if alpha_max < self.min_alpha or alpha_min >= 255:
                        continue
                    local_mask = alpha.point(
                        lambda value: (
                            255
                            if self.min_alpha <= value <= self.embedded_soft_mask_max_alpha
                            else 0
                        )
                    )
                    try:
                        # Strip 1 px soft-mask anti-alias rings; keep real fades/shadows.
                        if self.embedded_soft_mask_erode > 1:
                            eroded = local_mask.filter(
                                ImageFilter.MinFilter(self.embedded_soft_mask_erode)
                            )
                            local_mask.close()
                            local_mask = eroded
                        if self._count_mask_pixels(local_mask) < 1:
                            continue
                        target = self._bbox_to_preview_box(
                            bbox=bbox,
                            zoom_x=zoom_x,
                            zoom_y=zoom_y,
                            preview_size=page_mask.size,
                        )
                        if target is None:
                            continue
                        placed = local_mask.resize(
                            (target[2] - target[0], target[3] - target[1]),
                            Image.Resampling.NEAREST,
                        )
                        try:
                            region = page_mask.crop(target)
                            merged = ImageChops.lighter(region, placed)
                            try:
                                page_mask.paste(merged, target)
                            finally:
                                region.close()
                                merged.close()
                        finally:
                            placed.close()
                    finally:
                        local_mask.close()
                finally:
                    alpha.close()
            finally:
                embedded.close()

    def _accumulate_preview_opacity_mask(
        self,
        *,
        preview_image: Image.Image,
        page_mask: Image.Image,
    ) -> None:
        rgba = preview_image.convert("RGBA")
        try:
            alpha = rgba.getchannel("A")
            try:
                semi_mask = alpha.point(
                    lambda value: 255 if self.min_alpha <= value <= self.max_alpha else 0
                )
                try:
                    eroded = semi_mask.filter(ImageFilter.MinFilter(self.render_antialias_filter))
                    try:
                        if eroded.size != page_mask.size:
                            resized = eroded.resize(
                                page_mask.size,
                                Image.Resampling.NEAREST,
                            )
                            eroded.close()
                            eroded = resized
                        merged = ImageChops.lighter(page_mask, eroded)
                        page_mask.paste(merged)
                        merged.close()
                    finally:
                        eroded.close()
                finally:
                    semi_mask.close()
            finally:
                alpha.close()
        finally:
            rgba.close()

    @staticmethod
    def _extract_embedded_rgba(
        *,
        document: pymupdf.Document,
        xref: int,
        smask_xref: int,
    ) -> Image.Image | None:
        try:
            pixmap = pymupdf.Pixmap(document, xref)
        except (RuntimeError, ValueError):
            return None
        try:
            if smask_xref > 0:
                try:
                    soft_mask = pymupdf.Pixmap(document, smask_xref)
                except (RuntimeError, ValueError):
                    soft_mask = None
                if soft_mask is not None:
                    try:
                        pixmap = pymupdf.Pixmap(pixmap, soft_mask)
                    finally:
                        soft_mask = None
            if not pixmap.alpha:
                return None
            mode = "RGBA" if pixmap.n >= 4 else "LA"
            return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)
        except (RuntimeError, ValueError, OSError):
            return None

    @staticmethod
    def _bbox_to_preview_box(
        *,
        bbox,
        zoom_x: float,
        zoom_y: float,
        preview_size: tuple[int, int],
    ) -> tuple[int, int, int, int] | None:
        x0, y0, x1, y1 = (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        left = max(0, int(round(min(x0, x1) * zoom_x)))
        top = max(0, int(round(min(y0, y1) * zoom_y)))
        right = min(preview_size[0], int(round(max(x0, x1) * zoom_x)))
        bottom = min(preview_size[1], int(round(max(y0, y1) * zoom_y)))
        if right - left < 1 or bottom - top < 1:
            return None
        return left, top, right, bottom

    @staticmethod
    def _preview_zoom(
        *,
        preview_size: tuple[int, int],
        page_width_points: float | None,
        page_height_points: float | None,
        page: pymupdf.Page,
    ) -> tuple[float, float]:
        width_pts = float(page_width_points or page.rect.width or 1.0)
        height_pts = float(page_height_points or page.rect.height or 1.0)
        return (
            preview_size[0] / max(width_pts, 1.0),
            preview_size[1] / max(height_pts, 1.0),
        )

    def _build_overlay(self, semi_mask: Image.Image) -> bytes:
        dilate = max(int(self.overlay_dilate), 1)
        visible_mask = (
            semi_mask.filter(ImageFilter.MaxFilter(dilate)) if dilate > 1 else semi_mask.copy()
        )
        try:
            visible_mask.thumbnail(
                (self.max_overlay_side, self.max_overlay_side),
                Image.Resampling.LANCZOS,
            )
            alpha = visible_mask.point(lambda value: min(180, round(value * 0.7)))
            try:
                overlay = Image.new(
                    "RGBA",
                    visible_mask.size,
                    (*self.overlay_rgb, 0),
                )
                try:
                    overlay.putalpha(alpha)
                    output = BytesIO()
                    overlay.save(output, format="WEBP", lossless=True, method=4)
                    return output.getvalue()
                finally:
                    overlay.close()
            finally:
                alpha.close()
        finally:
            visible_mask.close()

    def _empty_result(
        self,
        *,
        skip_reason: str | None = None,
        alpha_channel_present: bool | None = None,
    ) -> SemiTransparencyAnalysisResult:
        return SemiTransparencyAnalysisResult(
            detected=False,
            overlay=None,
            metadata={
                "detected": False,
                "min_alpha": self.min_alpha,
                "max_alpha": self.max_alpha,
                "min_pixels": self.min_pixels,
                "min_coverage_percent": self.min_coverage_percent,
                "pixel_count": 0,
                "coverage_percent": 0.0,
                "alpha_channel_present": alpha_channel_present,
                "analysis_mode": "skipped" if skip_reason else "empty",
                "skipped": skip_reason is not None,
                "skip_reason": skip_reason,
            },
        )

    @staticmethod
    def _has_native_alpha(image: Image.Image) -> bool:
        if image.mode in {"RGBA", "LA", "PA", "RGBa"}:
            return True
        if "transparency" in image.info:
            return True
        return False

    @staticmethod
    def _count_mask_pixels(mask: Image.Image) -> int:
        histogram = mask.histogram()
        return sum(histogram[128:])
