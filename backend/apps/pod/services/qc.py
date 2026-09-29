from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditlog.services import record_event
from apps.pod.models import PodRipWorkItem, PodShopifyOrder, PodUnit, ShopifyStore
from apps.pod.services.validation import require_staff_perm, validation_message


def is_pod_order_qc_ready(order: PodShopifyOrder) -> bool:
    """Return whether an identified Shopify POD order is wholly QC-approved."""

    if (
        not order.pk
        or not order.customer_id
        or not order.store_id
        or order.store.customer_id != order.customer_id
    ):
        return False
    items = list(
        order.work_items.select_related("store", "variant__product__store").prefetch_related(
            "units__lot"
        )
    )
    if not items:
        return False
    if any(
        item.status in {PodRipWorkItem.Status.QUEUED, PodRipWorkItem.Status.SKIPPED}
        or item.skip_reason.startswith("Commande Shopify annulée")
        for item in items
    ):
        return False
    active_items = [item for item in items if item.status != PodRipWorkItem.Status.CANCELLED]
    if not active_items or any(
        item.status != PodRipWorkItem.Status.INCLUDED for item in active_items
    ):
        return False
    for item in active_items:
        if (
            item.store_id != order.store_id
            or item.variant.product.store_id != order.store_id
            or item.shopify_order_id != order.pk
        ):
            return False
        units = list(item.units.all())
        if len(units) != item.quantity:
            return False
        if any(
            unit.status != PodUnit.Status.QC_PASSED
            or unit.variant_id != item.variant_id
            or unit.lot.customer_id != order.customer_id
            for unit in units
        ):
            return False
    return True


class PodQcService:
    """Scan-first quality decisions for a single, already pressed POD piece."""

    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.operate_pod_production"

    @staticmethod
    def _scan(scan_identifier: str) -> str:
        scan = (scan_identifier or "").strip().upper()
        if not scan:
            raise ValidationError("Scannez un identifiant pièce.")
        return scan

    @staticmethod
    def _unit_queryset():
        return PodUnit.objects.select_related(
            "work_item",
            "work_item__store",
            "variant",
            "variant__product",
            "lot",
        )

    def lookup(self, *, actor, scan_identifier: str) -> dict:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.qc",
            action="pod.qc.permission_rejected",
        )
        unit = self._unit_queryset().filter(scan_identifier=self._scan(scan_identifier)).first()
        if unit is None:
            raise ValidationError("Pièce introuvable.")
        return {
            "unit": unit,
            "checks": list(
                unit.quality_checks.select_related("checked_by").order_by("-created_at")[:20]
            ),
        }

    def list_pending(self, *, actor, limit: int = 30) -> list[PodUnit]:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.qc",
            action="pod.qc.permission_rejected",
        )
        safe_limit = min(max(int(limit), 1), 100)
        return list(
            self._unit_queryset()
            .filter(status=PodUnit.Status.PRESSED)
            .order_by("pressed_at", "created_at")[:safe_limit]
        )

    @staticmethod
    def _assert_owned_and_active(unit: PodUnit) -> None:
        store = unit.work_item.store
        if (
            not store.customer_id
            or unit.lot.customer_id != store.customer_id
            or unit.variant.product.store_id != store.pk
        ):
            raise ValidationError("Boutique, client ou pièce incohérents : contrôle bloqué.")
        if unit.work_item.skip_reason.startswith("Commande Shopify annulée"):
            raise ValidationError("Commande Shopify annulée : contrôle bloqué.")

    def decide(
        self,
        *,
        actor,
        scan_identifier: str,
        passed: bool,
        defect_code: str = "",
        note: str = "",
        source: str = "staff_pod",
    ) -> PodUnit:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.qc.permission_rejected",
        )
        scan = self._scan(scan_identifier)
        if not isinstance(passed, bool):
            raise ValidationError("Décision qualité invalide.")
        defect = (defect_code or "").strip()
        detail = (note or "").strip()
        if not passed and not defect:
            raise ValidationError("Le motif du refus est obligatoire.")
        if len(defect) > 80 or len(detail) > 500:
            raise ValidationError("Motif ou note de contrôle trop long.")
        from apps.pod.models import PodQualityCheck

        try:
            with transaction.atomic():
                identity = (
                    PodUnit.objects.filter(scan_identifier=scan)
                    .values_list("work_item__store_id", "work_item__shopify_order_id")
                    .first()
                )
                if identity is None:
                    raise ValidationError("Pièce introuvable.")
                store_id, pod_order_id = identity
                ShopifyStore.objects.select_for_update(of=("self",)).get(pk=store_id)
                if pod_order_id:
                    PodShopifyOrder.objects.select_for_update(of=("self",)).get(pk=pod_order_id)
                unit = (
                    self._unit_queryset()
                    .select_for_update(of=("self",))
                    .filter(scan_identifier=scan)
                    .first()
                )
                if unit is None:
                    raise ValidationError("Pièce introuvable.")
                if (
                    unit.work_item.store_id != store_id
                    or unit.work_item.shopify_order_id != pod_order_id
                ):
                    raise ValidationError("Commande Shopify modifiée pendant le contrôle.")
                self._assert_owned_and_active(unit)
                target = PodUnit.Status.QC_PASSED if passed else PodUnit.Status.QC_FAILED
                if unit.status == target:
                    return unit  # A repeated POST must not append another decision.
                if unit.status != PodUnit.Status.PRESSED:
                    raise ValidationError(
                        "Seule une pièce posée et en attente de QC peut être contrôlée."
                    )
                check = PodQualityCheck.objects.create(
                    unit=unit,
                    result=(PodQualityCheck.Result.PASS if passed else PodQualityCheck.Result.FAIL),
                    defect_code="" if passed else defect,
                    note=detail,
                    checked_by=actor,
                )
                unit.status = target
                unit.save(update_fields=["status", "updated_at"])
                record_event(
                    action="pod.qc.passed" if passed else "pod.qc.failed",
                    actor=actor,
                    target=unit,
                    metadata={
                        "source": source,
                        "check_public_id": str(check.public_id),
                        "defect_code": "" if passed else defect,
                    },
                )
                if passed and unit.work_item.shopify_order_id:
                    from apps.notifications.services.workshop_push import (
                        WorkshopNotificationService,
                    )

                    WorkshopNotificationService().publish_pod_order_qc_ready(
                        pod_order=unit.work_item.shopify_order,
                        check=check,
                        actor=actor,
                        source=source,
                    )
                return unit
        except ValidationError as exc:
            record_event(
                action="pod.qc.rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise

    def reopen(self, *, actor, scan_identifier: str, source: str = "staff_pod") -> PodUnit:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.qc.permission_rejected",
        )
        scan = self._scan(scan_identifier)
        with transaction.atomic():
            unit = (
                self._unit_queryset()
                .select_for_update(of=("self",))
                .filter(scan_identifier=scan)
                .first()
            )
            if unit is None:
                raise ValidationError("Pièce introuvable.")
            self._assert_owned_and_active(unit)
            if unit.status == PodUnit.Status.PRESSED:
                return unit
            if unit.status != PodUnit.Status.QC_FAILED:
                raise ValidationError("Seule une pièce refusée peut être reprise après correction.")
            unit.status = PodUnit.Status.PRESSED
            unit.save(update_fields=["status", "updated_at"])
            record_event(
                action="pod.qc.reopened",
                actor=actor,
                target=unit,
                metadata={"source": source},
            )
            return unit
