from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageFilter


@dataclass(frozen=True)
class SemiTransparencyAnalysisResult:
    detected: bool
    overlay: bytes | None
    metadata: dict[str, object]


class AssetSemiTransparencyAnalyzer:
    """Detect partial alpha values that are unreliable in DTF printing."""

    min_alpha = 33
    max_alpha = 250
    min_pixels = 48
    max_overlay_side = 480
    overlay_rgb = (255, 152, 0)

    def analyze(self, *, image: Image.Image) -> SemiTransparencyAnalysisResult:
        rgba = image.convert("RGBA")
        try:
            alpha = rgba.getchannel("A")
            try:
                alpha_min, alpha_max = alpha.getextrema()
                if alpha_max <= self.min_alpha or alpha_min >= 255:
                    return self._empty_result()

                semi_mask = alpha.point(
                    lambda value: 255 if self.min_alpha <= value <= self.max_alpha else 0
                )
                try:
                    semi_pixels = self._count_mask_pixels(semi_mask)
                    total_pixels = alpha.width * alpha.height
                    coverage_percent = round((semi_pixels / total_pixels) * 100, 2)
                    detected = semi_pixels >= self.min_pixels
                    overlay = self._build_overlay(semi_mask) if detected else None
                finally:
                    semi_mask.close()
            finally:
                alpha.close()
        finally:
            rgba.close()

        return SemiTransparencyAnalysisResult(
            detected=detected,
            overlay=overlay,
            metadata={
                "detected": detected,
                "min_alpha": self.min_alpha,
                "max_alpha": self.max_alpha,
                "pixel_count": semi_pixels,
                "coverage_percent": coverage_percent,
            },
        )

    def _build_overlay(self, semi_mask: Image.Image) -> bytes:
        visible_mask = semi_mask.filter(ImageFilter.MaxFilter(3))
        try:
            visible_mask.thumbnail(
                (self.max_overlay_side, self.max_overlay_side),
                Image.Resampling.LANCZOS,
            )
            alpha = visible_mask.point(lambda value: min(210, round(value * 0.82)))
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

    def _empty_result(self) -> SemiTransparencyAnalysisResult:
        return SemiTransparencyAnalysisResult(
            detected=False,
            overlay=None,
            metadata={
                "detected": False,
                "min_alpha": self.min_alpha,
                "max_alpha": self.max_alpha,
                "pixel_count": 0,
                "coverage_percent": 0.0,
            },
        )

    @staticmethod
    def _count_mask_pixels(mask: Image.Image) -> int:
        histogram = mask.histogram()
        return sum(histogram[128:])
