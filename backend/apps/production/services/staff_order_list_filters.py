from __future__ import annotations

from django.db.models import Count, Exists, OuterRef, Q, QuerySet

from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.uploads.models import OrderUpload, OrderUploadReview


class StaffOrderListFilterService:
    """Filtres opérationnels de la liste staff /staff/orders/."""

    default_queue = ""
    queue_definitions = (
        ("", "Toutes"),
        ("unprinted", "OF non imprimés"),
        ("to_review", "À contrôler"),
        ("changes", "Corrections"),
        ("approved", "Fichiers validés"),
    )

    def normalize_queue(self, queue: str | None) -> str:
        allowed = {key for key, _label in self.queue_definitions}
        cleaned = str(queue or "").strip()
        return cleaned if cleaned in allowed else self.default_queue

    def label_for(self, queue: str) -> str:
        for key, label in self.queue_definitions:
            if key == queue:
                return label
        return self.queue_definitions[0][1]

    def build_tabs(self, *, active_queue: str, counts: dict[str, int]) -> list[dict[str, object]]:
        return [
            {
                "key": key,
                "label": label,
                "count": counts.get(key, 0),
                "is_active": key == active_queue,
            }
            for key, label in self.queue_definitions
        ]

    def count_by_queue(self, queryset: QuerySet) -> dict[str, int]:
        base = queryset.exclude(status=Order.Status.CANCELLED)
        unissued = self._unissued_queryset_from(base)
        return {
            "": base.count(),
            "unprinted": unissued.count(),
            "to_review": self._filter_to_review(unissued).count(),
            "changes": self._filter_changes(unissued).count(),
            "approved": self._filter_approved(unissued).count(),
        }

    def apply_filter(self, queryset: QuerySet, *, queue: str) -> QuerySet:
        normalized = self.normalize_queue(queue)
        if not normalized:
            return queryset
        if normalized == "unprinted":
            return self._unissued_queryset_from(queryset)
        unissued = self._unissued_queryset_from(queryset)
        if normalized == "to_review":
            return self._filter_to_review(unissued)
        if normalized == "changes":
            return self._filter_changes(unissued)
        if normalized == "approved":
            return self._filter_approved(unissued)
        return queryset

    def apply_search(self, queryset: QuerySet, *, query: str) -> QuerySet:
        cleaned = str(query or "").strip()
        if not cleaned:
            return queryset

        return queryset.filter(
            Q(production_job__manufacturing_order_number__icontains=cleaned)
            | Q(source_b2b_order_project__project_number__icontains=cleaned)
            | Q(source_b2b_order_project__name__icontains=cleaned)
            | Q(source_b2b_order_project__customer_reference__icontains=cleaned)
            | Q(customer__name__icontains=cleaned)
            | Q(customer_note__icontains=cleaned)
        ).distinct()

    def _unissued_queryset_from(self, queryset: QuerySet) -> QuerySet:
        return (
            queryset.filter(
                status=Order.Status.SUBMITTED,
                production_job__of_document_issued_at__isnull=True,
            )
            .exclude(production_job__status=ProductionJob.Status.COMPLETED)
            .distinct()
        )

    def _filter_changes(self, queryset: QuerySet) -> QuerySet:
        has_changes = Exists(
            OrderUpload.objects.filter(
                order_id=OuterRef("pk"),
                atelier_review__status=OrderUploadReview.Status.CHANGES_REQUESTED,
            )
        )
        return queryset.annotate(_has_changes=has_changes).filter(_has_changes=True).distinct()

    def _filter_to_review(self, queryset: QuerySet) -> QuerySet:
        has_changes = Exists(
            OrderUpload.objects.filter(
                order_id=OuterRef("pk"),
                atelier_review__status=OrderUploadReview.Status.CHANGES_REQUESTED,
            )
        )
        has_pending = Exists(
            OrderUpload.objects.filter(order_id=OuterRef("pk")).filter(
                Q(atelier_review__isnull=True)
                | Q(atelier_review__status=OrderUploadReview.Status.PENDING)
            )
        )
        return (
            queryset.annotate(
                _upload_count=Count("uploads", distinct=True),
                _has_changes=has_changes,
                _has_pending=has_pending,
            )
            .filter(
                Q(_upload_count=0) | (Q(_has_pending=True) & Q(_has_changes=False)),
            )
            .distinct()
        )

    def _filter_approved(self, queryset: QuerySet) -> QuerySet:
        has_non_approved = Exists(
            OrderUpload.objects.filter(order_id=OuterRef("pk")).filter(
                Q(atelier_review__isnull=True)
                | ~Q(atelier_review__status=OrderUploadReview.Status.APPROVED)
            )
        )
        return (
            queryset.annotate(
                _upload_count=Count("uploads", distinct=True),
                _has_non_approved=has_non_approved,
            )
            .filter(_upload_count__gt=0, _has_non_approved=False)
            .distinct()
        )
