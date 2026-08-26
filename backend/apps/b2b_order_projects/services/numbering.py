from django.db import transaction
from django.utils import timezone

from apps.b2b_order_projects.models import B2BOrderProject, B2BOrderProjectNumberSequence

PROJECT_NUMBER_PREFIX_GANG_SHEET = "GANG-SHEET"
PROJECT_NUMBER_PREFIX_FILE_ORDER = "CMD"
# Conservé pour compatibilité des imports/tests historiques.
PROJECT_NUMBER_PREFIX = PROJECT_NUMBER_PREFIX_GANG_SHEET


def project_number_prefix_for_order_mode(order_mode: str) -> str:
    if order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET:
        return PROJECT_NUMBER_PREFIX_GANG_SHEET
    return PROJECT_NUMBER_PREFIX_FILE_ORDER


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
