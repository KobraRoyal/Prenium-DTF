from __future__ import annotations

from decimal import Decimal

SUPPORT_COLOR_MULTICOLOR = "#multicolor"


def _source_value(upload, name: str, default=None):
    if isinstance(upload, dict):
        return upload.get(name, default)
    return getattr(upload, name, default)


def _listed_visual(*, file_name: str, quantity, color: str) -> dict[str, object]:
    is_multicolor = color == SUPPORT_COLOR_MULTICOLOR
    return {
        "file_name": file_name,
        "quantity": quantity or 1,
        "support_color_hex": "" if is_multicolor else color,
        "support_color_is_multicolor": is_multicolor,
    }


def listed_visuals(upload) -> list[dict[str, object]]:
    """Une ligne par visuel. Un fichier classique reste une ligne. Un lien se déplie."""

    specs = [
        spec
        for spec in (_source_value(upload, "external_visual_specs", None) or [])
        if isinstance(spec, dict)
    ]
    if _source_value(upload, "is_external", False) and specs:
        return [
            _listed_visual(
                file_name=str(spec.get("file_name") or "").strip() or f"Visuel {index}",
                quantity=spec.get("quantity"),
                color=str(spec.get("support_color_hex") or ""),
            )
            for index, spec in enumerate(specs, start=1)
        ]
    color = str(_source_value(upload, "support_color_hex", "") or "")
    if not color:
        color = str(_source_value(upload, "support_color", "") or "")
    return [
        _listed_visual(
            file_name=str(_source_value(upload, "original_filename", "") or ""),
            quantity=_source_value(upload, "quantity", 1),
            color=color,
        )
    ]


class OrderUploadProductionSpecService:
    """Construit les consignes client figées pour le contrôle et la production."""

    def serialize(self, *, order_upload) -> dict[str, object]:
        has_dimensions = bool(order_upload.width_mm and order_upload.height_mm)
        specs = [
            spec for spec in (order_upload.external_visual_specs or []) if isinstance(spec, dict)
        ]
        support_label = order_upload.support_color_label or "Non renseignée"
        if specs and not order_upload.support_color_hex:
            support_label = "Par visuel"
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
            "support_color_label": support_label,
            "support_color_is_multicolor": order_upload.support_color_is_multicolor,
            "external_visual_specs": specs,
        }

    def _format_decimal(self, value: Decimal | None) -> str:
        if value is None:
            return ""
        return format(value, "f").rstrip("0").rstrip(".").replace(".", ",")
