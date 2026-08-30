from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.pod.models import PodUnit
from apps.pod.services.documents import PodUnitDocumentService
from apps.pod.services.validation import require_staff_perm


class PodUnitAccessService:
    view_permission = "pod.access_pod_atelier"

    def get_unit(self, *, actor, unit_public_id) -> PodUnit:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.unit",
            action="pod.unit.permission_rejected",
        )
        unit = PodUnit.objects.filter(public_id=unit_public_id).first()
        if unit is None:
            raise ValidationError("Pièce introuvable.")
        return unit

    def document_path(self, *, actor, unit_public_id, kind: str):
        unit = self.get_unit(actor=actor, unit_public_id=unit_public_id)
        return unit, PodUnitDocumentService().document_path(unit=unit, kind=kind)
