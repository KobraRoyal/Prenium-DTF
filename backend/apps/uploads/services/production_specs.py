from __future__ import annotations

from decimal import Decimal


class OrderUploadProductionSpecService:
    """Construit les consignes client figées pour le contrôle et la production."""

    def serialize(self, *, order_upload) -> dict[str, object]:
        has_dimensions = bool(order_upload.width_mm and order_upload.height_mm)
        return {
            "width_mm": self._format_decimal(order_upload.width_mm),
            "height_mm": self._format_decimal(order_upload.height_mm),
            "has_dimensions": has_dimensions,
            "dimensions_label": (
                f"{self._format_decimal(order_upload.width_mm)} × "
                f"{self._format_decimal(order_upload.height_mm)} mm"
                if has_dimensions
                else "Non renseignée"
            ),
            "support_color": order_upload.support_color_hex,
            "support_color_label": order_upload.support_color_label or "Non renseignée",
            "support_color_is_multicolor": order_upload.support_color_is_multicolor,
        }

    def _format_decimal(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return format(value, "f").rstrip("0").rstrip(".").replace(".", ",")
