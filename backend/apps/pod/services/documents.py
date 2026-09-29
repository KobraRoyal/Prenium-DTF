from __future__ import annotations

import uuid
from pathlib import Path

from django.core.exceptions import ValidationError

from apps.pod.models import PodPickSessionLine, PodRipLot, PodUnit


def new_scan_identifier() -> str:
    return f"POD-{uuid.uuid4().hex[:10].upper()}"


class PodUnitDocumentService:
    """Crée les PodUnit du lot RIP.

    Les PDF OF / étiquettes atelier sont générés à la session picking
    (liste A4 + Zebra). Le lot RIP ne fait que lier le scan picking → unité.
    """

    def create_units_for_lot(self, *, lot: PodRipLot, planned: list[dict]) -> list[PodUnit]:
        seen_items = []
        units = []
        item_ids = list({entry["work_item"].pk for entry in planned})
        pick_by_piece = {
            (line.work_item_id, line.sequence): line
            for line in PodPickSessionLine.objects.filter(
                work_item_id__in=item_ids,
                voided_at__isnull=True,
            )
        }
        for entry in planned:
            item = entry["work_item"]
            if item.pk in seen_items:
                continue
            seen_items.append(item.pk)
            qty = max(int(item.quantity or 1), 1)
            for sequence in range(1, qty + 1):
                pick_line = pick_by_piece.get((item.pk, sequence))
                if pick_line is None:
                    raise ValidationError(
                        f"Étiquette picking manquante pour {item.shopify_order_number} "
                        f"pièce {sequence}/{qty}."
                    )
                scan_id = pick_line.scan_identifier
                unit = PodUnit.objects.create(
                    lot=lot,
                    work_item=item,
                    variant=item.variant,
                    sequence=sequence,
                    scan_identifier=scan_id,
                    of_relative_path="",
                    label_relative_path="",
                )
                if pick_line.unit_id is None:
                    pick_line.unit = unit
                    pick_line.save(update_fields=["unit", "updated_at"])
                units.append(unit)
        return units

    def document_path(self, *, unit: PodUnit, kind: str) -> Path:
        relative = unit.of_relative_path if kind == "of" else unit.label_relative_path
        if kind not in {"of", "etiquette"} or not relative:
            raise ValidationError(
                "Document pièce indisponible : utilisez la liste picking et les étiquettes Zebra "
                "de la session."
            )
        root = self._nas_root().resolve()
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValidationError("Chemin document invalide.") from exc
        if not path.is_file():
            raise ValidationError("Fichier NAS introuvable.")
        return path

    def _nas_root(self):
        from django.conf import settings

        return Path(settings.MEDIA_ROOT) / "pod_rip"
