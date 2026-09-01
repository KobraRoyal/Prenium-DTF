from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import PodUnit
from apps.pod.services.validation import require_staff_perm, validation_message
from apps.pod.services.variant_config import VariantConfigService


class PodPoseService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.manage_pod_catalog"

    def __init__(self):
        self.variant_config_service = VariantConfigService()

    def lookup(self, *, actor, scan_identifier: str) -> dict:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.pose",
            action="pod.pose.permission_rejected",
        )
        scan = (scan_identifier or "").strip().upper()
        if not scan:
            raise ValidationError("Scannez un identifiant pièce.")
        unit = (
            PodUnit.objects.select_related(
                "variant__product__store",
                "variant__ids_config__blank_variant__blank",
                "work_item",
                "lot",
            )
            .prefetch_related("variant__ids_config__recipe__slots__technique")
            .filter(scan_identifier=scan)
            .first()
        )
        if unit is None:
            raise ValidationError("Pièce introuvable.")
        config = getattr(unit.variant, "ids_config", None)
        slots = []
        recipe = None
        if config is not None and hasattr(config, "recipe"):
            recipe = config.recipe
        if recipe is not None:
            slots = list(recipe.slots.filter(is_enabled=True).select_related("technique"))
        return {"unit": unit, "config": config, "slots": slots}

    def mark_pressed(self, *, actor, scan_identifier: str, source: str) -> PodUnit:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.pose.permission_rejected",
        )
        try:
            context = self.lookup(actor=actor, scan_identifier=scan_identifier)
            unit = context["unit"]
            if unit.status == PodUnit.Status.PRESSED:
                raise ValidationError("Cette pièce est déjà posée.")
            unit.status = PodUnit.Status.PRESSED
            unit.pressed_at = timezone.now()
            unit.pressed_by = actor
            unit.save(update_fields=["status", "pressed_at", "pressed_by", "updated_at"])
            record_event(
                action="pod.pose.pressed",
                actor=actor,
                target=unit,
                metadata={"source": source, "scan": unit.scan_identifier},
            )
            return unit
        except ValidationError as exc:
            record_event(
                action="pod.pose.rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise
