from __future__ import annotations

import uuid

import pymupdf
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Count, F, Q

from apps.auditlog.services import record_event
from apps.core.public_refs import short_public_ref
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.manufacturing_order_pdf import (
    render_manufacturing_order_pdf_bytes,
)
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUploadReview


class ManufacturingOrderBatchService:
    max_batch_size = 20
    latest_ready_limit = 5

    def __init__(self):
        self.workflow_service = ProductionWorkflowService()

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
            },
        )
        return pdf_bytes, orders

    def resolve_orders(
        self,
        *,
        order_public_ids: list[str],
        mode: str,
    ) -> list[Order]:
        if mode == "latest_ready":
            orders = list(self._ready_queryset()[: self.latest_ready_limit])
            if not orders:
                raise ValidationError("Aucun OF prêt à imprimer pour le moment.")
            return orders
        if mode != "selected":
            raise ValidationError("Mode d'impression OF invalide.")

        normalized_ids = self._normalize_public_ids(order_public_ids)
        orders = list(
            self._document_queryset().filter(public_id__in=normalized_ids).order_by("-created_at")
        )
        if len(orders) != len(normalized_ids):
            raise ValidationError("Une commande sélectionnée est introuvable.")

        blocked_refs = [
            short_public_ref(order.public_id).upper()
            for order in orders
            if not self._is_print_eligible(order=order)
        ]
        if blocked_refs:
            refs = ", ".join(f"#{reference}" for reference in blocked_refs[:5])
            raise ValidationError(f"Validez tous les fichiers Atelier avant impression : {refs}.")
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

    def _document_queryset(self):
        return (
            Order.objects.filter(status=Order.Status.SUBMITTED)
            .select_related("customer", "production_job")
            .prefetch_related(
                "items",
                "uploads",
                "uploads__inspection",
                "uploads__atelier_review",
                "uploads__drive_sync",
                "production_job__transitions",
            )
        )

    def _ready_queryset(self):
        return (
            self._document_queryset()
            .filter(production_job__status=ProductionJob.Status.QUEUED)
            .annotate(
                batch_upload_count=Count("uploads", distinct=True),
                batch_approved_count=Count(
                    "uploads",
                    filter=Q(uploads__atelier_review__status=OrderUploadReview.Status.APPROVED),
                    distinct=True,
                ),
            )
            .filter(
                batch_upload_count__gt=0,
                batch_upload_count=F("batch_approved_count"),
            )
            .order_by("-created_at")
        )

    def _is_print_eligible(self, *, order: Order) -> bool:
        uploads = list(order.uploads.all())
        if not uploads:
            return False
        if any(
            self._review_status(upload) != OrderUploadReview.Status.APPROVED for upload in uploads
        ):
            return False
        try:
            production_job = order.production_job
        except ProductionJob.DoesNotExist:
            return False
        return production_job.status != ProductionJob.Status.COMPLETED

    def _review_status(self, upload) -> str:
        try:
            return upload.atelier_review.status
        except ObjectDoesNotExist:
            return OrderUploadReview.Status.PENDING
