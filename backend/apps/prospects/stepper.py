from __future__ import annotations

from typing import TypedDict

# Libellés courts + aide — cohérents avec le tunnel simplifié en trois étapes.
PROSPECT_STEP_META: tuple[tuple[str, str], ...] = (
    ("Entreprise", "Identité vérifiée"),
    ("Projet", "Besoin & volume"),
    ("Validation", "Récapitulatif"),
)


class ProspectStepperItem(TypedDict):
    label: str
    help: str
    is_current: bool
    is_complete: bool


def stepper_items_for_step(current_step: int, total_steps: int = 3) -> list[ProspectStepperItem]:
    """Éléments pour `prospects/partials/stepper.html` (état courant / complété)."""
    if total_steps < 1:
        return []
    current_step = max(1, min(current_step, total_steps))
    items: list[ProspectStepperItem] = []
    for i in range(1, total_steps + 1):
        label, help_text = (
            PROSPECT_STEP_META[i - 1] if i <= len(PROSPECT_STEP_META) else (f"Étape {i}", "")
        )
        items.append(
            {
                "label": label,
                "help": help_text,
                "is_current": i == current_step,
                "is_complete": i < current_step,
            }
        )
    return items
