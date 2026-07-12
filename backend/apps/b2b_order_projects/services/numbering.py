from django.db import transaction
from django.utils import timezone

from apps.b2b_order_projects.models import B2BOrderProjectNumberSequence


class B2BOrderProjectNumberService:
    @transaction.atomic
    def next_number(self) -> str:
        year = timezone.localdate().year
        B2BOrderProjectNumberSequence.objects.get_or_create(year=year)
        sequence = B2BOrderProjectNumberSequence.objects.select_for_update().get(year=year)
        value = sequence.next_value
        sequence.next_value = value + 1
        sequence.save(update_fields=["next_value"])
        return f"DTF-B2B-{year}-{value:06d}"
