from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageChops, ImageFilter


@dataclass(frozen=True)
class ThinZoneAnalysisResult:
    detected: bool
    overlay: bytes | None
    metadata: dict[str, object]


class AssetThinZoneAnalyzer:
    """Detect printed details thinner than a physical production threshold."""

    threshold_mm = 0.5
    fallback_dpi = 300.0
    alpha_threshold = 32
    white_background_threshold = 245
    max_overlay_side = 480
    max_kernel_size = 51

    def analyze(
        self,
        *,
        image: Image.Image,
        dpi_x: float | None,
        dpi_y: float | None,
        metadata: dict[str, object],
        probable_white_background: bool,
    ) -> ThinZoneAnalysisResult:
        pixels_per_mm, scale_basis = self._pixels_per_mm(
            image=image,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
            metadata=metadata,
        )
        threshold_pixels = max(pixels_per_mm * self.threshold_mm, 1.0)
        kernel_size = self._opening_kernel_size(threshold_pixels)
        foreground, mask_basis = self._foreground_mask(
            image=image,
            probable_white_background=probable_white_background,
        )
        try:
            foreground_pixels = self._count_mask_pixels(foreground)
            if foreground_pixels == 0:
                return self._empty_result(
                    threshold_pixels=threshold_pixels,
                    kernel_size=kernel_size,
                    scale_basis=scale_basis,
                    mask_basis=mask_basis,
                )

            opened = foreground.filter(ImageFilter.MinFilter(kernel_size)).filter(
                ImageFilter.MaxFilter(kernel_size)
            )
            try:
                thin_mask = ImageChops.subtract(foreground, opened)
                try:
                    thin_mask = thin_mask.point(lambda value: 255 if value >= 128 else 0)
                    thin_pixels = self._count_mask_pixels(thin_mask)
                    detected = thin_pixels >= 4
                    coverage_percent = round((thin_pixels / foreground_pixels) * 100, 2)
                    overlay = self._build_overlay(thin_mask) if detected else None
                finally:
                    thin_mask.close()
            finally:
                opened.close()
        finally:
            foreground.close()

        return ThinZoneAnalysisResult(
            detected=detected,
            overlay=overlay,
            metadata={
                "detected": detected,
                "threshold_mm": self.threshold_mm,
                "threshold_pixels": round(threshold_pixels, 2),
                "kernel_size": kernel_size,
                "coverage_percent": coverage_percent,
                "scale_basis": scale_basis,
                "mask_basis": mask_basis,
            },
        )

    def _pixels_per_mm(
        self,
        *,
        image: Image.Image,
        dpi_x: float | None,
        dpi_y: float | None,
        metadata: dict[str, object],
    ) -> tuple[float, str]:
        artboard_width_mm = self._positive_float(metadata.get("artboard_width_mm"))
        artboard_height_mm = self._positive_float(metadata.get("artboard_height_mm"))
        if metadata.get("uses_artboard_dimensions") and artboard_width_mm and artboard_height_mm:
            return (
                min(
                    image.width / artboard_width_mm,
                    image.height / artboard_height_mm,
                ),
                "artboard_dimensions",
            )

        page_width_in = self._positive_float(metadata.get("page_width_in"))
        page_height_in = self._positive_float(metadata.get("page_height_in"))
        if page_width_in and page_height_in:
            return (
                min(
                    image.width / (page_width_in * 25.4),
                    image.height / (page_height_in * 25.4),
                ),
                "page_dimensions",
            )

        x = self._positive_float(dpi_x)
        y = self._positive_float(dpi_y)
        if x and y:
            return min(x, y) / 25.4, "embedded_dpi"

        render_dpi = self._positive_float(metadata.get("render_dpi"))
        if render_dpi:
            return render_dpi / 25.4, "render_dpi"
        return self.fallback_dpi / 25.4, "fallback_300_dpi"

    def _foreground_mask(
        self,
        *,
        image: Image.Image,
        probable_white_background: bool,
    ) -> tuple[Image.Image, str]:
        rgba = image.convert("RGBA")
        try:
            alpha = rgba.getchannel("A")
            alpha_extrema = alpha.getextrema()
            if alpha_extrema[0] < 250:
                mask = alpha.point(lambda value: 255 if value >= self.alpha_threshold else 0)
                alpha.close()
                return mask, "transparency"
            alpha.close()

            if probable_white_background:
                rgb = rgba.convert("RGB")
                try:
                    return (
                        rgb.convert("L").point(
                            lambda value: (255 if value < self.white_background_threshold else 0)
                        ),
                        "non_white_pixels",
                    )
                finally:
                    rgb.close()

            return Image.new("L", rgba.size, 255), "opaque_artboard"
        finally:
            rgba.close()

    def _build_overlay(self, thin_mask: Image.Image) -> bytes:
        visible_mask = thin_mask.filter(ImageFilter.MaxFilter(3))
        try:
            visible_mask.thumbnail(
                (self.max_overlay_side, self.max_overlay_side),
                Image.Resampling.LANCZOS,
            )
            alpha = visible_mask.point(lambda value: min(220, round(value * 0.86)))
            try:
                overlay = Image.new("RGBA", visible_mask.size, (239, 44, 72, 0))
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
        threshold_pixels: float,
        kernel_size: int,
        scale_basis: str,
        mask_basis: str,
    ) -> ThinZoneAnalysisResult:
        return ThinZoneAnalysisResult(
            detected=False,
            overlay=None,
            metadata={
                "detected": False,
                "threshold_mm": self.threshold_mm,
                "threshold_pixels": round(threshold_pixels, 2),
                "kernel_size": kernel_size,
                "coverage_percent": 0.0,
                "scale_basis": scale_basis,
                "mask_basis": mask_basis,
            },
        )

    def _opening_kernel_size(self, threshold_pixels: float) -> int:
        size = max(3, math.ceil(threshold_pixels))
        odd_size = size if size % 2 else size + 1
        return min(odd_size, self.max_kernel_size)

    @staticmethod
    def _count_mask_pixels(mask: Image.Image) -> int:
        histogram = mask.histogram()
        return sum(histogram[128:])

    @staticmethod
    def _positive_float(value) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
