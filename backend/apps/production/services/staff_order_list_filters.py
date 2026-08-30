from __future__ import annotations

from datetime import timedelta

from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Q, QuerySet, Value, When
from django.utils import timezone

from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.uploads.models import OrderUpload, OrderUploadReview


def annotate_processing_time_priority(queryset: QuerySet) -> QuerySet:
    """Priorité opérationnelle : express (0) → rapide (1) → standard (2) → legacy (3)."""
    return queryset.annotate(
        processing_time_priority=Case(
            When(processing_time_code="express", then=Value(0)),
            When(processing_time_code="fast", then=Value(1)),
            When(processing_time_code="standard", then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    )


def order_by_operational_priority(queryset: QuerySet) -> QuerySet:
    """Tri file atelier : délai le plus urgent d'abord, puis date commande décroissante."""
    return annotate_processing_time_priority(queryset).order_by(
        "processing_time_priority",
        "-created_at",
    )


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
    default_period = ""
    period_definitions = (
        ("", "Toutes dates"),
        ("today", "Aujourd'hui"),
        ("7d", "7 jours"),
        ("30d", "30 jours"),
    )

    def normalize_queue(self, queue: str | None) -> str:
        allowed = {key for key, _label in self.queue_definitions}
        cleaned = str(queue or "").strip()
        return cleaned if cleaned in allowed else self.default_queue

    def normalize_period(self, period: str | None) -> str:
        allowed = {key for key, _label in self.period_definitions}
        cleaned = str(period or "").strip()
        return cleaned if cleaned in allowed else self.default_period

    def label_for_period(self, period: str) -> str:
        for key, label in self.period_definitions:
            if key == period:
                return label
        return self.period_definitions[0][1]

    def build_period_tabs(self, *, active_period: str) -> list[dict[str, object]]:
        return [
            {
                "key": key,
                "label": label,
                "is_active": key == active_period,
            }
            for key, label in self.period_definitions
        ]

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
        issued = self._issued_queryset_from(base)
        return {
            "": base.count(),
            "unprinted": unissued.count(),
            "to_review": self._filter_to_review(issued).count(),
            "changes": self._filter_changes(issued).count(),
            "approved": self._filter_approved(issued).count(),
        }

    def apply_filter(self, queryset: QuerySet, *, queue: str) -> QuerySet:
        normalized = self.normalize_queue(queue)
        if not normalized:
            return queryset
        if normalized == "unprinted":
            return self._unissued_queryset_from(queryset)
        issued = self._issued_queryset_from(queryset)
        if normalized == "to_review":
            return self._filter_to_review(issued)
        if normalized == "changes":
            return self._filter_changes(issued)
        if normalized == "approved":
            return self._filter_approved(issued)
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

    def apply_period_filter(self, queryset: QuerySet, *, period: str) -> QuerySet:
        normalized = self.normalize_period(period)
        if not normalized:
            return queryset
        now = timezone.now()
        if normalized == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif normalized == "7d":
            start = now - timedelta(days=7)
        elif normalized == "30d":
            start = now - timedelta(days=30)
        else:
            return queryset
        return queryset.filter(created_at__gte=start)

    def apply_operational_order(self, queryset: QuerySet) -> QuerySet:
        return order_by_operational_priority(queryset)

    def _unissued_queryset_from(self, queryset: QuerySet) -> QuerySet:
        return self._active_queryset_from(queryset).filter(
            production_job__of_document_issued_at__isnull=True,
        )

    def _issued_queryset_from(self, queryset: QuerySet) -> QuerySet:
        return self._active_queryset_from(queryset).filter(
            production_job__of_document_issued_at__isnull=False,
        )

    def _active_queryset_from(self, queryset: QuerySet) -> QuerySet:
        return (
            queryset.filter(
                status=Order.Status.SUBMITTED,
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
