from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VariantSlotPayload:
    placement: str
    technique_public_id: str
    is_enabled: bool = True
    print_reference: str = ""
    display_order: int = 0


@dataclass(frozen=True)
class VariantConfigPayload:
    """Contrat partagé staff portal et future app Shopify."""

    mode: str
    blank_variant_public_id: str | None = None
    finished_sku: str = ""
    staff_locked: bool = False
    slots: tuple[VariantSlotPayload, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> VariantConfigPayload:
        slots = tuple(
            VariantSlotPayload(
                placement=str(item.get("placement", "")).strip(),
                technique_public_id=str(item.get("technique_public_id", "")).strip(),
                is_enabled=bool(item.get("is_enabled", True)),
                print_reference=str(item.get("print_reference", "")).strip(),
                display_order=int(item.get("display_order", 0) or 0),
            )
            for item in data.get("slots") or []
        )
        return cls(
            mode=str(data.get("mode", "unmanaged")).strip().lower(),
            blank_variant_public_id=(data.get("blank_variant_public_id") or None),
            finished_sku=str(data.get("finished_sku", "")).strip().upper(),
            staff_locked=bool(data.get("staff_locked")),
            slots=slots,
        )
