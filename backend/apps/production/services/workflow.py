from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.formats import date_format

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.core.public_refs import short_public_ref
from apps.orders.models import Order
from apps.production.models import ProductionJob, ProductionJobTransition
from apps.uploads.services.production_specs import OrderUploadProductionSpecService

production_spec_service = OrderUploadProductionSpecService()


class ProductionWorkflowService:
    document_status_labels = {
        Order.Status.DRAFT: "Brouillon",
        Order.Status.SUBMITTED: "Soumise",
        ProductionJob.Status.QUEUED: "En attente Atelier",
        ProductionJob.Status.IN_PROGRESS: "En production",
        ProductionJob.Status.BLOCKED: "Bloqué",
        ProductionJob.Status.READY_TO_SHIP: "Prêt à expédier",
        ProductionJob.Status.COMPLETED: "Terminé",
    }

    allowed_transitions = {
        ProductionJob.Status.QUEUED: {
            ProductionJob.Status.IN_PROGRESS,
            ProductionJob.Status.BLOCKED,
        },
        ProductionJob.Status.IN_PROGRESS: {
            ProductionJob.Status.BLOCKED,
            ProductionJob.Status.READY_TO_SHIP,
        },
        ProductionJob.Status.BLOCKED: {
            ProductionJob.Status.QUEUED,
            ProductionJob.Status.IN_PROGRESS,
        },
        ProductionJob.Status.READY_TO_SHIP: {
            ProductionJob.Status.COMPLETED,
        },
        ProductionJob.Status.COMPLETED: set(),
    }

    def allowed_target_statuses(self, *, current_status: str) -> list[str]:
        """Retourne les cibles autorisées dans l'ordre métier affiché par l'UI."""
        allowed = self.allowed_transitions.get(current_status, set())
        return [status for status in ProductionJob.Status.values if status in allowed]

    def get_or_create_for_order(self, *, order: Order) -> ProductionJob:
        mo_number = self.build_manufacturing_order_number(order=order)
        production_job, _created = ProductionJob.objects.get_or_create(
            order=order,
            defaults={
                "manufacturing_order_number": mo_number,
                # Une seule référence « type GPAO » : OF + scan / code-barres identiques.
                "scan_identifier": mo_number,
                "status": ProductionJob.Status.QUEUED,
                "last_transition_at": order.created_at,
            },
        )
        return production_job

    def build_manufacturing_order_number(self, *, order: Order) -> str:
        return f"OF-{order.created_at:%Y%m%d}-{str(order.public_id).split('-')[0].upper()}"

    def get_staff_job(self, *, order_public_id, actor, source: str):
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None

        production_job = self.get_or_create_for_order(order=order)
        production_job = self._get_job_queryset().filter(pk=production_job.pk).first()
        self.record_view_event(
            production_job=production_job,
            actor=actor,
            source=source,
        )
        return order, production_job

    def get_staff_job_for_document(self, *, order_public_id):
        """Charge commande + job atelier sans journaliser de vue (PDF, exports)."""
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None
        production_job = self.get_or_create_for_order(order=order)
        production_job = self._get_job_queryset().filter(pk=production_job.pk).first()
        return order, production_job

    def transition_job(
        self,
        *,
        order_public_id,
        to_status: str,
        actor,
        source: str,
        reason: str = "",
    ):
        order = self._get_staff_order(order_public_id=order_public_id)
        if order is None:
            return None, None, None

        production_job = self.get_or_create_for_order(order=order)
        production_job = self._get_job_queryset().filter(pk=production_job.pk).first()
        return order, *self._apply_transition(
            production_job=production_job,
            actor=actor,
            source=source,
            to_status=to_status,
            reason=reason,
        )

    def transition_existing_job(
        self,
        *,
        production_job: ProductionJob,
        actor,
        source: str,
        to_status: str,
        reason: str = "",
    ):
        return self._apply_transition(
            production_job=production_job,
            actor=actor,
            source=source,
            to_status=to_status,
            reason=reason,
        )

    def _serialize_order_items_for_document(
        self,
        *,
        order: Order,
    ) -> tuple[list[dict[str, object]], str]:
        lines = list(order.items.all().order_by("position"))
        if lines:
            return (
                [
                    {
                        "public_id": str(item.public_id),
                        "service_code": item.service_code,
                        "service_name": item.service_name,
                        "service_type": item.service_type,
                        "unit": item.unit,
                        "quantity": f"{item.quantity:.2f}",
                        "unit_price": f"{item.unit_price:.2f}",
                        "line_total": f"{item.line_total:.2f}",
                    }
                    for item in lines
                ],
                "order_lines",
            )
        return (
            [
                {
                    "public_id": str(upload.public_id),
                    "service_code": "fichier_client",
                    "service_name": upload.original_filename,
                    "service_type": "upload",
                    "unit": "piece",
                    "quantity": f"{upload.quantity}",
                    "unit_price": "-",
                    "line_total": "-",
                }
                for upload in order.uploads.all().order_by("sort_order", "created_at")
            ],
            "upload_fallback",
        )

    def _serialize_upload_for_document(self, *, order_upload) -> dict[str, object]:
        inspection = self._safe_related_object(order_upload, relation_name="inspection")
        review = self._safe_related_object(order_upload, relation_name="atelier_review")
        drive_sync = self._safe_related_object(order_upload, relation_name="drive_sync")
        production_specs = production_spec_service.serialize(order_upload=order_upload)

        return {
            "public_id": str(order_upload.public_id),
            "original_filename": order_upload.original_filename,
            "quantity": order_upload.quantity,
            "mime_type": order_upload.mime_type,
            "size_bytes": order_upload.size_bytes,
            **production_specs,
            "inspection_status": inspection.status if inspection is not None else None,
            "inspection_status_label": (
                inspection.get_status_display() if inspection is not None else "Non analysé"
            ),
            "inspection_summary": (inspection.summary_message if inspection is not None else ""),
            "atelier_review_status": review.status if review is not None else "pending",
            "atelier_review_status_label": (
                review.get_status_display() if review is not None else "À contrôler"
            ),
            "atelier_review_reason": review.reason_code if review is not None else "",
            "atelier_review_reason_label": (
                review.get_reason_code_display()
                if review is not None and review.reason_code
                else ""
            ),
            "atelier_review_comment": review.comment if review is not None else "",
            "drive_sync_status": drive_sync.status if drive_sync is not None else None,
        }

    def _build_file_review_summary(
        self,
        *,
        uploads: list[dict[str, object]],
    ) -> dict[str, object]:
        approved = sum(upload["atelier_review_status"] == "approved" for upload in uploads)
        changes_requested = sum(
            upload["atelier_review_status"] == "changes_requested" for upload in uploads
        )
        pending = len(uploads) - approved - changes_requested
        return {
            "total": len(uploads),
            "approved": approved,
            "pending": pending,
            "changes_requested": changes_requested,
            "ready_for_production": bool(uploads) and approved == len(uploads),
        }

    def build_manufacturing_order(
        self,
        *,
        order: Order,
        production_job: ProductionJob,
    ) -> dict[str, object]:
        items, items_source = self._serialize_order_items_for_document(order=order)
        uploads = [
            self._serialize_upload_for_document(order_upload=order_upload)
            for order_upload in order.uploads.all().order_by("sort_order", "created_at")
        ]
        order_created_at = timezone.localtime(order.created_at)

        return {
            "document_type": "manufacturing_order_v1",
            "number": production_job.manufacturing_order_number,
            "order_public_id": str(order.public_id),
            "production_job_public_id": str(production_job.public_id),
            "scan": self.build_scan_payload(production_job=production_job),
            "customer": {
                "public_id": str(order.customer.public_id),
                "name": order.customer.name,
            },
            "order_summary": {
                "reference": short_public_ref(order.public_id).upper(),
                "status": order.status,
                "status_label": self.document_status_labels.get(order.status, order.status),
                "currency": order.currency,
                "subtotal_amount": f"{order.subtotal_amount:.2f}",
                "total_amount": f"{order.total_amount:.2f}",
                "customer_note": order.customer_note,
                "created_at": order.created_at.isoformat(),
                "created_at_label": date_format(order_created_at, "d/m/Y H:i"),
            },
            "production_summary": {
                "status": production_job.status,
                "status_label": self.document_status_labels.get(
                    production_job.status,
                    production_job.status,
                ),
                "started_at": production_job.started_at.isoformat()
                if production_job.started_at
                else None,
                "completed_at": production_job.completed_at.isoformat()
                if production_job.completed_at
                else None,
                "last_transition_at": production_job.last_transition_at.isoformat()
                if production_job.last_transition_at
                else None,
            },
            "items": items,
            "items_source": items_source,
            "uploads": uploads,
            "file_review_summary": self._build_file_review_summary(uploads=uploads),
            "transitions": [
                self.serialize_transition(transition)
                for transition in production_job.transitions.all()
            ],
        }

    def build_scan_payload(self, *, production_job: ProductionJob) -> dict[str, object]:
        return {
            "identifier": production_job.scan_identifier,
            "barcode": {
                "format": "code128",
                "value": production_job.scan_identifier,
            },
            "qr_code": {
                "value": production_job.scan_identifier,
            },
        }

    def serialize_transition(self, transition: ProductionJobTransition) -> dict[str, object]:
        return {
            "public_id": str(transition.public_id),
            "from_status": transition.from_status,
            "to_status": transition.to_status,
            "reason": transition.reason,
            "source": transition.source,
            "changed_at": transition.created_at.isoformat(),
            "changed_by": {
                "public_id": str(transition.changed_by.public_id),
                "email": transition.changed_by.email,
            }
            if transition.changed_by is not None
            else None,
        }

    def record_view_event(self, *, production_job: ProductionJob, actor, source: str) -> None:
        record_event(
            action="production.job_viewed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=production_job,
            metadata={
                "order_public_id": str(production_job.order.public_id),
                "customer_public_id": str(production_job.order.customer.public_id),
                "production_job_public_id": str(production_job.public_id),
                "manufacturing_order_number": production_job.manufacturing_order_number,
                "production_status": production_job.status,
                "source": source,
            },
        )

    def _apply_transition(
        self,
        *,
        production_job: ProductionJob,
        actor,
        source: str,
        to_status: str,
        reason: str,
    ):
        normalized_status = str(to_status).strip()
        normalized_reason = str(reason).strip()

        if normalized_status not in ProductionJob.Status.values:
            self._record_rejected_transition(
                production_job=production_job,
                actor=actor,
                source=source,
                message="Unknown target status.",
                requested_status=normalized_status,
            )
            raise ValidationError("Unknown target status.")

        now = timezone.now()
        rejection_message = None
        locked_job = None
        notification_event = None

        with transaction.atomic():
            locked_job = (
                ProductionJob.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=production_job.pk)
            )
            from_status = locked_job.status
            allowed_targets = self.allowed_transitions.get(from_status, set())

            if normalized_status not in allowed_targets:
                rejection_message = (
                    f"Transition from {from_status} to {normalized_status} is not allowed."
                )
            else:
                is_first_processing = (
                    normalized_status == ProductionJob.Status.IN_PROGRESS
                    and locked_job.started_at is None
                )
                locked_job.status = normalized_status
                locked_job.last_transition_at = now
                locked_job.last_transition_by = (
                    actor if getattr(actor, "is_authenticated", False) else None
                )
                locked_job.last_transition_note = normalized_reason[:255]
                if (
                    normalized_status == ProductionJob.Status.IN_PROGRESS
                    and locked_job.started_at is None
                ):
                    locked_job.started_at = now
                if normalized_status == ProductionJob.Status.COMPLETED:
                    locked_job.completed_at = now

                locked_job.save(
                    update_fields=[
                        "status",
                        "started_at",
                        "completed_at",
                        "last_transition_at",
                        "last_transition_by",
                        "last_transition_note",
                        "updated_at",
                    ]
                )

                transition = ProductionJobTransition.objects.create(
                    production_job=locked_job,
                    from_status=from_status,
                    to_status=normalized_status,
                    changed_by=actor if getattr(actor, "is_authenticated", False) else None,
                    reason=normalized_reason[:255],
                    source=source,
                )

                record_event(
                    action="production.status_changed",
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    target=locked_job,
                    metadata={
                        "order_public_id": str(locked_job.order.public_id),
                        "customer_public_id": str(locked_job.order.customer.public_id),
                        "production_job_public_id": str(locked_job.public_id),
                        "manufacturing_order_number": locked_job.manufacturing_order_number,
                        "production_transition_public_id": str(transition.public_id),
                        "from_status": from_status,
                        "to_status": normalized_status,
                        "reason": normalized_reason[:255],
                        "source": source,
                    },
                )

                if is_first_processing:
                    notification_event = "processing"
                elif normalized_status == ProductionJob.Status.READY_TO_SHIP:
                    notification_event = "ready_to_ship"

        if rejection_message is not None:
            self._record_rejected_transition(
                production_job=locked_job,
                actor=actor,
                source=source,
                message=rejection_message,
                requested_status=normalized_status,
            )
            raise ValidationError("Transition not allowed from the current status.")

        if notification_event == "processing":
            from apps.notifications.services.transactional import (
                schedule_order_processing_email,
            )

            schedule_order_processing_email(order_public_id=locked_job.order.public_id)
        elif notification_event == "ready_to_ship":
            from apps.notifications.services.transactional import (
                schedule_order_ready_to_ship_email,
            )

            schedule_order_ready_to_ship_email(order_public_id=locked_job.order.public_id)

        locked_job = self._get_job_queryset().filter(pk=locked_job.pk).first()
        return locked_job, transition

    def _record_rejected_transition(
        self,
        *,
        production_job: ProductionJob,
        actor,
        source: str,
        message: str,
        requested_status: str,
    ) -> None:
        record_event(
            action="production.transition_rejected",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=production_job,
            status=AuditLogEntry.Status.FAILURE,
            message=message,
            metadata={
                "order_public_id": str(production_job.order.public_id),
                "customer_public_id": str(production_job.order.customer.public_id),
                "production_job_public_id": str(production_job.public_id),
                "manufacturing_order_number": production_job.manufacturing_order_number,
                "current_status": production_job.status,
                "requested_status": requested_status,
                "source": source,
            },
        )

    def _get_staff_order(self, *, order_public_id):
        return (
            Order.objects.select_related("customer", "created_by")
            .prefetch_related(
                "items",
                "uploads",
                "uploads__inspection",
                "uploads__atelier_review",
                "uploads__drive_sync",
            )
            .filter(public_id=order_public_id)
            .first()
        )

    def _get_job_queryset(self):
        return ProductionJob.objects.select_related(
            "order",
            "order__customer",
            "order__created_by",
            "last_transition_by",
        ).prefetch_related(
            "transitions",
            "transitions__changed_by",
            "scan_logs",
            "scan_logs__actor",
            "order__items",
            "order__uploads",
            "order__uploads__inspection",
            "order__uploads__atelier_review",
            "order__uploads__drive_sync",
        )

    def _safe_related_object(self, instance, *, relation_name: str):
        try:
            return getattr(instance, relation_name)
        except ObjectDoesNotExist:
            return None
