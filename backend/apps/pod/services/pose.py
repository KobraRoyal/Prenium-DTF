from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import PodPickSessionLine, PodUnit
from apps.pod.services.operate_workflow import PodOperateWorkflowService
from apps.pod.services.validation import require_staff_perm, validation_message
from apps.pod.services.variant_config import VariantConfigService


class PodPoseService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.operate_pod_production"

    def __init__(self):
        self.variant_config_service = VariantConfigService()
        self.operate = PodOperateWorkflowService()

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
        unit = self._resolve_unit(scan)
        if unit is None:
            raise ValidationError("Pièce introuvable.")
        if unit.status == PodUnit.Status.ISSUE:
            raise ValidationError(
                "Cette pièce est gelée (commande annulée ou incident). "
                "Elle ne peut plus être posée."
            )
        if unit.status == PodUnit.Status.PRESSED:
            raise ValidationError("Cette pièce est déjà posée.")
        config = getattr(unit.variant, "ids_config", None)
        slots = []
        recipe = None
        if config is not None and hasattr(config, "recipe"):
            recipe = config.recipe
        if recipe is not None:
            slots = list(recipe.slots.filter(is_enabled=True).select_related("technique"))
        return {"unit": unit, "config": config, "slots": slots}

    def _resolve_unit(self, scan: str) -> PodUnit | None:
        unit_qs = PodUnit.objects.select_related(
            "variant__product__store",
            "variant__ids_config__blank_variant__blank",
            "work_item",
            "lot",
        ).prefetch_related("variant__ids_config__recipe__slots__technique")
        unit = unit_qs.filter(scan_identifier=scan).first()
        if unit is not None:
            self.operate.require_pose_unlocked(unit=unit)
            self._require_blank_picked_for_unit(unit=unit, scan=scan)
            return unit
        pick_line = (
            PodPickSessionLine.objects.select_related("unit", "work_item")
            .filter(scan_identifier=scan, voided_at__isnull=True)
            .first()
        )
        if pick_line is None:
            return None
        if pick_line.unit_id:
            unit = unit_qs.filter(pk=pick_line.unit_id).first()
            if unit is not None:
                self.operate.require_pose_unlocked(unit=unit)
                self._require_blank_picked_for_unit(unit=unit, scan=scan, pick_line=pick_line)
                return unit
        matched = unit_qs.filter(
            work_item_id=pick_line.work_item_id,
            sequence=pick_line.sequence,
        ).first()
        if matched is not None:
            self.operate.require_pose_unlocked(unit=matched)
            self._require_blank_picked_for_unit(unit=matched, scan=scan, pick_line=pick_line)
            return matched
        raise ValidationError(self._missing_unit_message(pick_line=pick_line, scan=scan))

    def _require_blank_picked_for_unit(
        self,
        *,
        unit: PodUnit,
        scan: str,
        pick_line: PodPickSessionLine | None = None,
    ) -> None:
        line = pick_line
        if line is None:
            line = (
                PodPickSessionLine.objects.select_related("work_item")
                .filter(scan_identifier=scan, voided_at__isnull=True)
                .first()
            )
        if line is None:
            return
        if line.reservation_status != PodPickSessionLine.ReservationStatus.PICKED:
            order = line.work_item.shopify_order_number if line.work_item_id else ""
            raise ValidationError(
                f"Étiquette {scan} ({order or 'commande'}) : le lot DTF est prêt, "
                "mais le support n’est pas encore sorti du stock. "
                "Scannez pièce + bin sur À produire avant la pose."
            )

    def _missing_unit_message(self, *, pick_line: PodPickSessionLine, scan: str) -> str:
        order = pick_line.work_item.shopify_order_number if pick_line.work_item_id else ""
        status = pick_line.get_reservation_status_display()
        prefix = f"Étiquette picking {scan} ({order or 'commande'}, {status})"
        if pick_line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED:
            return (
                f"{prefix} : prélèvement OK, mais le lot DTF n’a pas encore été lancé. "
                "Sur À produire, « Préparer lot DTF » (possible avant ou après le prélèvement), "
                "puis revenez au poste Pose."
            )
        if pick_line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED:
            return (
                f"{prefix} : lot DTF pas encore lancé. "
                "Sur À produire, « Préparer lot DTF » puis imprimez ; "
                "le prélèvement support peut suivre ou précéder l’impression."
            )
        if pick_line.reservation_status == PodPickSessionLine.ReservationStatus.UNTRACKED:
            return (
                f"{prefix} : étiquette legacy sans réservation. "
                "Contrôlez la pièce physique, puis régénérez une session picking si besoin."
            )
        return (
            f"{prefix} : pas encore de pièce atelier. "
            "Terminez le prélèvement puis préparez le lot DTF depuis À produire."
        )

    def mark_pressed(self, *, actor, scan_identifier: str, source: str) -> PodUnit:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.pose.permission_rejected",
        )
        try:
            with transaction.atomic():
                context = self.lookup(actor=actor, scan_identifier=scan_identifier)
                unit = (
                    PodUnit.objects.select_for_update(of=("self",))
                    .select_related("work_item", "work_item__store", "variant__product", "lot")
                    .get(pk=context["unit"].pk)
                )
                if unit.status != PodUnit.Status.WAITING_PRESS:
                    raise ValidationError("Cette pièce n'est plus en attente de pose.")
                if not context["slots"]:
                    raise ValidationError("Aucun slot de production actif pour cette pièce.")
                if (
                    unit.work_item.skip_reason.startswith("Commande Shopify annulée")
                    or not unit.work_item.store.customer_id
                    or unit.lot.customer_id != unit.work_item.store.customer_id
                    or unit.variant.product.store_id != unit.work_item.store_id
                ):
                    raise ValidationError(
                        "Commande ou appartenance client incohérente : pose bloquée."
                    )
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
