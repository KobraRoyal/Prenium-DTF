from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Prefetch, Q, When

from apps.billing.models import Payment
from apps.billing.services.production_payment_gate import production_start_blocked_reason
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService


class AtelierOperationsService:
    """Construit la console de pilotage sans porter les mutations metier."""

    page_size = 25
    default_queue = "active"
    queue_definitions = (
        ("active", "À traiter"),
        ("shipping", "À expédier"),
        ("completed", "Terminés"),
        ("all", "Tous"),
    )
    active_statuses = (
        ProductionJob.Status.BLOCKED,
        ProductionJob.Status.IN_PROGRESS,
        ProductionJob.Status.QUEUED,
    )
    action_labels = {
        ProductionJob.Status.QUEUED: "Remettre en file",
        ProductionJob.Status.IN_PROGRESS: "Démarrer la production",
        ProductionJob.Status.READY_TO_SHIP: "Déclarer prêt à expédier",
        ProductionJob.Status.BLOCKED: "Bloquer l'OF",
        ProductionJob.Status.COMPLETED: "Terminer l'OF",
    }

    def __init__(self):
        self.workflow_service = ProductionWorkflowService()

    def build_workspace(
        self,
        *,
        queue: str | None,
        query: str | None,
        page_number,
        include_shipping: bool,
    ) -> dict[str, object]:
        normalized_queue = self._normalize_queue(queue)
        normalized_query = str(query or "").strip()[:80]
        base_queryset = self._base_queryset(include_shipping=include_shipping)
        counts = self._queue_counts(base_queryset)
        filtered = self._filter_queue(base_queryset, normalized_queue)
        if normalized_query:
            filtered = self._filter_scan_query(filtered, normalized_query)

        page_obj = Paginator(filtered, self.page_size).get_page(page_number)
        rows = [
            self._serialize_job(job=job, include_shipping=include_shipping)
            for job in page_obj.object_list
        ]
        page_obj.object_list = rows
        focus_row = rows[0] if normalized_query and rows else None
        return {
            "rows": rows,
            "page_obj": page_obj,
            "queue": normalized_queue,
            "query": normalized_query,
            "focus_row": focus_row,
            "focus_match_count": len(rows) if normalized_query else 0,
            "tabs": [
                {
                    "key": key,
                    "label": label,
                    "count": counts[key],
                    "is_active": key == normalized_queue,
                }
                for key, label in self.queue_definitions
            ],
        }

    def _filter_scan_query(self, queryset, query: str):
        exact = queryset.filter(
            Q(manufacturing_order_number__iexact=query) | Q(scan_identifier__iexact=query)
        )
        if exact.exists():
            return exact
        return queryset.filter(
            Q(manufacturing_order_number__icontains=query)
            | Q(scan_identifier__icontains=query)
            | Q(order__customer__name__icontains=query)
        )

    def _base_queryset(self, *, include_shipping: bool):
        select_related = [
            "order",
            "order__customer",
            "assigned_machine",
            "last_transition_by",
        ]
        if include_shipping:
            select_related.append("order__shipment")
        return (
            ProductionJob.objects.filter(order__status=Order.Status.SUBMITTED)
            .select_related(*select_related)
            .prefetch_related(
                "order__items",
                "order__uploads",
                Prefetch(
                    "order__payments",
                    queryset=Payment.objects.filter(status=Payment.Status.CAPTURED).only(
                        "id", "order_id"
                    ),
                    to_attr="_captured_payments",
                ),
            )
            .annotate(
                print_count=Count("print_records", distinct=True),
                operation_priority=Case(
                    When(status=ProductionJob.Status.BLOCKED, then=0),
                    When(status=ProductionJob.Status.READY_TO_SHIP, then=1),
                    When(status=ProductionJob.Status.IN_PROGRESS, then=2),
                    When(status=ProductionJob.Status.QUEUED, then=3),
                    default=4,
                    output_field=IntegerField(),
                ),
            )
            .order_by("operation_priority", "-last_transition_at", "-updated_at")
        )

    def _serialize_job(self, *, job: ProductionJob, include_shipping: bool) -> dict[str, object]:
        shipment = None
        if include_shipping:
            try:
                shipment = job.order.shipment
            except ObjectDoesNotExist:
                shipment = None
        allowed_statuses = self.workflow_service.allowed_target_statuses(
            current_status=job.status,
            order=job.order,
        )
        start_block_reason = None
        if job.status in {ProductionJob.Status.QUEUED, ProductionJob.Status.BLOCKED}:
            start_block_reason = production_start_blocked_reason(job.order)
        focus_panel = self._focus_panel(job.status)
        return {
            "job": job,
            "order": job.order,
            "customer": job.order.customer,
            "shipment": shipment,
            "allowed_actions": [
                {
                    "status": status,
                    "label": self.action_labels[status],
                    "is_primary": status
                    in {
                        ProductionJob.Status.IN_PROGRESS,
                        ProductionJob.Status.READY_TO_SHIP,
                        ProductionJob.Status.COMPLETED,
                    },
                    "is_danger": status == ProductionJob.Status.BLOCKED,
                }
                for status in allowed_statuses
            ],
            "print_count": job.print_count,
            "start_block_reason": start_block_reason,
            "focus_panel": focus_panel,
            "workflow_hint": self._workflow_hint(
                job=job,
                print_count=job.print_count,
            ),
            "needs_shipping": bool(
                include_shipping
                and job.status == ProductionJob.Status.READY_TO_SHIP
                and shipment is None
            ),
        }

    def _focus_panel(self, status: str) -> str:
        mapping = {
            ProductionJob.Status.QUEUED: "production",
            ProductionJob.Status.BLOCKED: "production",
            ProductionJob.Status.IN_PROGRESS: "production",
            ProductionJob.Status.READY_TO_SHIP: "shipping",
            ProductionJob.Status.COMPLETED: "billing",
        }
        return mapping.get(status, "production")

    def _workflow_hint(self, *, job: ProductionJob, print_count: int) -> str:
        if job.status == ProductionJob.Status.QUEUED:
            if not job.assigned_machine_id:
                return (
                    "Contrôlez les fichiers, sélectionnez une machine s’il y en a "
                    "plusieurs, puis saisissez le métrage."
                )
            return "Saisissez le métrage, puis démarrez l’impression."
        if job.status == ProductionJob.Status.IN_PROGRESS:
            if print_count == 0:
                return "Confirmez l’impression après le métrage."
            return "Avancez le statut ou préparez l’expédition."
        if job.status == ProductionJob.Status.READY_TO_SHIP:
            return "Déclarez l’expédition Sendcloud ou terminez l’OF."
        if job.status == ProductionJob.Status.BLOCKED:
            return "Levez le blocage ou vérifiez les prérequis métier."
        if job.status == ProductionJob.Status.COMPLETED:
            return "Dossier terminé — consultation et facturation."
        return "Ouvrez le dossier pour l’action suivante."

    def _queue_counts(self, queryset) -> dict[str, int]:
        return {
            "active": queryset.filter(status__in=self.active_statuses).count(),
            "shipping": queryset.filter(status=ProductionJob.Status.READY_TO_SHIP).count(),
            "completed": queryset.filter(status=ProductionJob.Status.COMPLETED).count(),
            "all": queryset.count(),
        }

    def _normalize_queue(self, queue: str | None) -> str:
        allowed = {key for key, _label in self.queue_definitions}
        return queue if queue in allowed else self.default_queue

    def _filter_queue(self, queryset, queue: str):
        if queue == "active":
            return queryset.filter(status__in=self.active_statuses)
        if queue == "shipping":
            return queryset.filter(status=ProductionJob.Status.READY_TO_SHIP)
        if queue == "completed":
            return queryset.filter(status=ProductionJob.Status.COMPLETED)
        return queryset
