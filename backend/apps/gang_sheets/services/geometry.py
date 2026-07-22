from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from apps.gang_sheets.models import GangSheetItem

HUNDREDTH = Decimal("0.01")


@dataclass(frozen=True)
class Rect:
    public_id: str
    x: Decimal
    y: Decimal
    width: Decimal
    height: Decimal

    @property
    def right(self) -> Decimal:
        return self.x + self.width

    @property
    def bottom(self) -> Decimal:
        return self.y + self.height


class GangSheetGeometryService:
    def rect_for(self, item) -> Rect:
        return Rect(
            public_id=str(item.public_id),
            x=Decimal(item.x_mm),
            y=Decimal(item.y_mm),
            width=Decimal(item.effective_width_mm),
            height=Decimal(item.effective_height_mm),
        )

    def required_height(self, *, sheet, items) -> Decimal:
        bottoms = [self.rect_for(item).bottom for item in items]
        raw = (max(bottoms) if bottoms else Decimal("0")) + Decimal(sheet.margin_mm)
        raw = max(
            raw,
            Decimal(sheet.minimum_height_mm),
            Decimal(sheet.height_step_mm),
            Decimal("1.00"),
        )
        step = Decimal(sheet.height_step_mm)
        rounded = (raw / step).to_integral_value(rounding=ROUND_CEILING) * step
        return min(rounded.quantize(HUNDREDTH), Decimal(sheet.maximum_height_mm))

    def issues(self, *, sheet, items) -> list[dict[str, object]]:
        rects = [self.rect_for(item) for item in items]
        issues: list[dict[str, object]] = []
        for rect in rects:
            if (
                rect.x < 0
                or rect.y < 0
                or rect.right > sheet.width_mm
                or rect.bottom > sheet.height_mm
            ):
                issues.append(
                    {
                        "code": "overflow",
                        "item_public_ids": [rect.public_id],
                        "message": "Le visuel déborde de la planche.",
                    }
                )
        for index, first in enumerate(rects):
            for second in rects[index + 1 :]:
                if self.overlaps(first, second):
                    issues.append(
                        {
                            "code": "overlap",
                            "item_public_ids": [first.public_id, second.public_id],
                            "message": "Deux visuels se chevauchent.",
                        }
                    )
        return issues

    @staticmethod
    def overlaps(first: Rect, second: Rect) -> bool:
        return not (
            first.right <= second.x
            or second.right <= first.x
            or first.bottom <= second.y
            or second.bottom <= first.y
        )

    def auto_place(self, *, sheet, items) -> list:
        """Placement bottom-left déterministe avec choix automatique de rotation.

        Les plus grandes occurrences sont placées en premier. Chaque orientation
        est testée sur les arêtes déjà occupées ; le score minimise d'abord la
        hauteur finale, puis l'abscisse. Cette stratégie est plus compacte qu'un
        simple remplissage ligne par ligne tout en restant explicable et stable.
        """

        margin = Decimal(sheet.margin_mm)
        spacing_x = Decimal(sheet.item_spacing_x_mm)
        spacing_y = Decimal(sheet.item_spacing_y_mm)
        max_right = Decimal(sheet.width_mm) - margin
        max_bottom = Decimal(sheet.maximum_height_mm) - margin
        placed: list[Rect] = []
        ordered = sorted(
            items,
            key=lambda item: (
                -(Decimal(item.width_mm) * Decimal(item.height_mm)),
                -max(Decimal(item.width_mm), Decimal(item.height_mm)),
                str(item.public_id),
            ),
        )
        for item in ordered:
            rotations = [item.rotation]
            alternate = (int(item.rotation) + 90) % 360
            if alternate not in rotations:
                rotations.append(alternate)
            candidates = []
            xs = {margin}
            ys = {margin}
            for rect in placed:
                xs.add(rect.right + spacing_x)
                ys.add(rect.bottom + spacing_y)
            for rotation in rotations:
                if rotation in {90, 270}:
                    width, height = Decimal(item.height_mm), Decimal(item.width_mm)
                else:
                    width, height = Decimal(item.width_mm), Decimal(item.height_mm)
                for y in sorted(ys):
                    for x in sorted(xs):
                        candidate = Rect(str(item.public_id), x, y, width, height)
                        if candidate.right > max_right or candidate.bottom > max_bottom:
                            continue
                        padded = Rect(
                            candidate.public_id,
                            candidate.x - spacing_x,
                            candidate.y - spacing_y,
                            candidate.width + spacing_x * 2,
                            candidate.height + spacing_y * 2,
                        )
                        if any(self.overlaps(padded, existing) for existing in placed):
                            continue
                        candidates.append(
                            (candidate.bottom, candidate.x, candidate.y, rotation, candidate)
                        )
            if not candidates:
                # Position volontairement invalide : l'UI et la validation exposent
                # clairement l'impossibilité plutôt que de perdre une occurrence.
                rotation = int(item.rotation)
                candidate = Rect(
                    str(item.public_id),
                    margin,
                    max_bottom,
                    Decimal(item.effective_width_mm),
                    Decimal(item.effective_height_mm),
                )
            else:
                _bottom, _x, _y, rotation, candidate = min(candidates)
            item.x_mm = candidate.x.quantize(HUNDREDTH)
            item.y_mm = candidate.y.quantize(HUNDREDTH)
            item.rotation = rotation
            placed.append(candidate)
        return ordered


def normalize_rotation(value) -> int:
    rotation = int(value)
    if rotation not in GangSheetItem.Rotation.values:
        raise ValueError("La rotation doit être 0°, 90°, 180° ou 270°.")
    return rotation
