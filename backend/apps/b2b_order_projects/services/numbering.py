from django.db import transaction
from django.utils import timezone

from apps.b2b_order_projects.models import B2BOrderProject, B2BOrderProjectNumberSequence

PROJECT_NUMBER_PREFIX = "CMD"
# Alias historiques — séquence unique pour tous les modes (fichier, gang-sheet, réassort).
PROJECT_NUMBER_PREFIX_FILE_ORDER = PROJECT_NUMBER_PREFIX
PROJECT_NUMBER_PREFIX_GANG_SHEET = PROJECT_NUMBER_PREFIX


def project_number_prefix_for_order_mode(order_mode: str) -> str:
    """Retourne le préfixe métier unique, quel que soit le mode de commande."""
    return PROJECT_NUMBER_PREFIX


class B2BOrderProjectNumberService:
    @transaction.atomic
    def next_number(self, *, order_mode: str | None = None) -> str:
        year = timezone.localdate().year
        B2BOrderProjectNumberSequence.objects.get_or_create(year=year)
        sequence = B2BOrderProjectNumberSequence.objects.select_for_update().get(year=year)
        value = sequence.next_value
        sequence.next_value = value + 1
        sequence.save(update_fields=["next_value"])
        prefix = project_number_prefix_for_order_mode(
            order_mode or B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS
        )
        return f"{prefix}-{year}-{value:06d}"
