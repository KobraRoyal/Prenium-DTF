from __future__ import annotations

import uuid

import pymupdf
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Count
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.core.public_refs import short_public_ref
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.manufacturing_order_pdf import (
    render_manufacturing_order_pdf_bytes,
)
from apps.production.services.staff_order_list_filters import order_by_operational_priority
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUploadReview


class ManufacturingOrderBatchService:
    """Émission PDF OF depuis la tour de contrôle — sans validation Atelier préalable."""

    max_batch_size = 20

    def __init__(self):
        self.workflow_service = ProductionWorkflowService()

    def count_unissued_orders(self) -> int:
        return self._unissued_queryset().count()

    def list_unissued_orders(self, *, limit: int | None = None) -> list[Order]:
        queryset = self._unissued_queryset()
        if limit is None:
            return list(queryset)
        return list(queryset[:limit])

    def build_batch_pdf(
        self,
        *,
        actor,
        order_public_ids: list[str] | None = None,
        mode: str = "selected",
        source: str,
    ) -> tuple[bytes, list[Order]]:
        orders = self.resolve_orders(
            order_public_ids=order_public_ids or [],
            mode=mode,
        )
        output = pymupdf.open()
        try:
            for order in orders:
                production_job = self.workflow_service.get_or_create_for_order(order=order)
                single_pdf = render_manufacturing_order_pdf_bytes(
                    order=order,
                    production_job=production_job,
                )
                with pymupdf.open(stream=single_pdf, filetype="pdf") as source_pdf:
                    output.insert_pdf(source_pdf)
            pdf_bytes = output.tobytes(garbage=4, deflate=True)
        finally:
            output.close()

        self.mark_of_documents_issued(orders=orders, actor=actor, source=source)
        record_event(
            action="production.manufacturing_orders_batch_downloaded",
            actor=actor,
            metadata={
                "order_count": len(orders),
                "order_public_ids": [str(order.public_id) for order in orders],
                "manufacturing_order_numbers": [
                    order.production_job.manufacturing_order_number for order in orders
                ],
                "mode": mode,
                "source": source,
                "of_documents_marked_issued": True,
            },
        )
        return pdf_bytes, orders

    def resolve_orders(
        self,
        *,
        order_public_ids: list[str],
        mode: str,
    ) -> list[Order]:
        if mode in {"all_unprinted", "all_ready", "latest_ready"}:
            orders = self.list_unissued_orders(limit=self.max_batch_size)
            if not orders:
                raise ValidationError("Aucun OF non imprimé pour le moment.")
            return orders
        if mode != "selected":
            raise ValidationError("Mode d'impression OF invalide.")

        normalized_ids = self._normalize_public_ids(order_public_ids)
        orders = list(
            order_by_operational_priority(
                self._unissued_queryset().filter(public_id__in=normalized_ids)
            )
        )
        if len(orders) != len(normalized_ids):
            raise ValidationError("Une commande sélectionnée est introuvable ou déjà imprimée.")

        blocked_refs = [
            short_public_ref(order.public_id).upper()
            for order in orders
            if not self._is_batch_eligible(order=order)
        ]
        if blocked_refs:
            refs = ", ".join(f"#{reference}" for reference in blocked_refs[:5])
            raise ValidationError(f"Impression impossible pour : {refs}.")
        return orders

    def _normalize_public_ids(self, values: list[str]) -> list[uuid.UUID]:
        normalized = []
        seen = set()
        for value in values:
            try:
                public_id = uuid.UUID(str(value))
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError("Sélection OF invalide.") from exc
            if public_id in seen:
                continue
            normalized.append(public_id)
            seen.add(public_id)
        if not normalized:
            raise ValidationError("Sélectionnez au moins un OF à imprimer.")
        if len(normalized) > self.max_batch_size:
            raise ValidationError(f"Un lot est limité à {self.max_batch_size} OF.")
        return normalized

    def _unissued_queryset(self):
        queryset = (
            Order.objects.filter(status=Order.Status.SUBMITTED)
            .filter(
                production_job__of_document_issued_at__isnull=True,
            )
            .exclude(production_job__status=ProductionJob.Status.COMPLETED)
            .select_related("customer", "production_job", "source_b2b_order_project")
            .prefetch_related(
                "items",
                "uploads",
                "uploads__inspection",
                "uploads__atelier_review",
                "uploads__drive_sync",
                "production_job__transitions",
            )
            .annotate(batch_upload_count=Count("uploads", distinct=True))
        )
        return order_by_operational_priority(queryset)

    def _is_batch_eligible(self, *, order: Order) -> bool:
        try:
            production_job = order.production_job
        except ProductionJob.DoesNotExist:
            return False
        if production_job.of_document_issued_at is not None:
            return False
        if production_job.status == ProductionJob.Status.COMPLETED:
            return False
        return order.status == Order.Status.SUBMITTED

    def mark_of_documents_issued(self, *, orders: list[Order], actor, source: str) -> None:
        now = timezone.now()
        job_ids = []
        for order in orders:
            production_job = order.production_job
            if production_job.of_document_issued_at is None:
                job_ids.append(production_job.pk)
        if not job_ids:
            return
        ProductionJob.objects.filter(pk__in=job_ids, of_document_issued_at__isnull=True).update(
            of_document_issued_at=now,
            updated_at=now,
        )
        record_event(
            action="production.manufacturing_orders_marked_issued",
            actor=actor,
            metadata={
                "order_count": len(job_ids),
                "production_job_ids": job_ids,
                "source": source,
            },
        )

    def _review_status(self, upload) -> str:
        try:
            return upload.atelier_review.status
        except ObjectDoesNotExist:
            return OrderUploadReview.Status.PENDING
