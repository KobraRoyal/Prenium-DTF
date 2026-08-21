from __future__ import annotations

import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.orders.models import Order
from apps.production.models import (
    ProductionJob,
    ProductionJobMachineAssignment,
    ProductionMachine,
    ProductionPrintRecord,
)
from apps.production.services.workflow import ProductionWorkflowService


class ProductionPrintTrackingService:
    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
        "production.confirm_productionprint",
    )
    confirmable_statuses = {
        ProductionJob.Status.IN_PROGRESS,
        ProductionJob.Status.READY_TO_SHIP,
    }

    def __init__(self):
        self.access_scope_service = AccessScopeService()

    def confirm_print(
        self,
        *,
        order_public_id,
        actor,
        source: str,
        note: str = "",
        request_token=None,
    ) -> tuple[ProductionJob, ProductionPrintRecord, bool]:
        try:
            self._require_permissions(actor)
        except PermissionDenied:
            record_event(
                action="production.print.confirmation_rejected",
                actor=self._authenticated_actor(actor),
                status=AuditLogEntry.Status.FAILURE,
                message="Permission denied.",
                metadata={"source": source},
            )
            raise
        normalized_note = str(note).strip()[:255]

        order = Order.objects.filter(public_id=order_public_id).first()
        if order is None:
            message = "Dossier Atelier introuvable."
            record_event(
                action="production.print.confirmation_rejected",
                actor=self._authenticated_actor(actor),
                status=AuditLogEntry.Status.FAILURE,
                message=message,
                metadata={"source": source, "reason": "object_not_found"},
            )
            raise ValidationError(message)
        job = ProductionWorkflowService().get_or_create_for_order(order=order)
        try:
            token = self._normalize_token(request_token)
        except ValidationError as exc:
            self._record_rejection(
                job=job,
                actor=actor,
                source=source,
                message="; ".join(exc.messages),
            )
            raise

        existing = ProductionPrintRecord.objects.filter(request_token=token).first()
        if existing is not None:
            if existing.production_job_id != job.pk:
                message = "Ce jeton de confirmation appartient à un autre dossier."
                self._record_rejection(
                    job=job,
                    actor=actor,
                    source=source,
                    message=message,
                )
                raise ValidationError(message)
            return existing.production_job, existing, False
        locked_job = None
        try:
            with transaction.atomic():
                locked_job = (
                    ProductionJob.objects.select_for_update(of=("self",))
                    .select_related("order", "order__customer", "assigned_machine")
                    .get(pk=job.pk)
                )
                existing = ProductionPrintRecord.objects.filter(request_token=token).first()
                if existing is not None:
                    return locked_job, existing, False
                if locked_job.order.status == Order.Status.CANCELLED:
                    raise ValidationError("Une commande annulée ne peut pas être confirmée.")
                if locked_job.status not in self.confirmable_statuses:
                    raise ValidationError(
                        "L’impression peut être confirmée uniquement pendant "
                        "ou après la production."
                    )
                machine = locked_job.assigned_machine
                if machine is None:
                    raise ValidationError("Attribuez d’abord une imprimante à ce dossier.")
                if machine.status != ProductionMachine.Status.ACTIVE:
                    raise ValidationError("L’imprimante attribuée n’est plus disponible.")
                assignment = (
                    ProductionJobMachineAssignment.objects.select_for_update()
                    .filter(
                        production_job=locked_job,
                        machine=machine,
                        ended_at__isnull=True,
                    )
                    .first()
                )
                if assignment is None:
                    raise ValidationError("L’attribution machine courante est incohérente.")
                is_reprint = locked_job.print_records.exists()
                if is_reprint and not normalized_note:
                    raise ValidationError("Précisez le motif de cette réimpression.")

                now = timezone.now()
                if assignment.printing_started_at is None:
                    assignment.printing_started_at = now
                    assignment.save(update_fields=("printing_started_at", "updated_at"))
                try:
                    with transaction.atomic():
                        print_record = ProductionPrintRecord.objects.create(
                            production_job=locked_job,
                            machine=machine,
                            assignment=assignment,
                            recorded_by=self._authenticated_actor(actor),
                            printed_at=now,
                            source=source,
                            note=normalized_note,
                            request_token=token,
                            machine_public_id_snapshot=machine.public_id,
                            machine_code_snapshot=machine.code,
                            machine_name_snapshot=machine.name,
                            manufacturing_order_number_snapshot=(
                                locked_job.manufacturing_order_number
                            ),
                            order_public_id_snapshot=locked_job.order.public_id,
                            customer_public_id_snapshot=locked_job.order.customer.public_id,
                        )
                except IntegrityError as exc:
                    winner = ProductionPrintRecord.objects.filter(request_token=token).first()
                    if winner is not None and winner.production_job_id == locked_job.pk:
                        return locked_job, winner, False
                    message = "Ce jeton de confirmation appartient à un autre dossier."
                    if winner is None:
                        message = "Conflit de confirmation d’impression, veuillez réessayer."
                    raise ValidationError(message) from exc
                record_event(
                    action=(
                        "production.print.reconfirmed"
                        if is_reprint
                        else "production.print.confirmed"
                    ),
                    actor=self._authenticated_actor(actor),
                    target=print_record,
                    metadata={
                        "customer_public_id": str(locked_job.order.customer.public_id),
                        "order_public_id": str(locked_job.order.public_id),
                        "production_job_public_id": str(locked_job.public_id),
                        "manufacturing_order_number": locked_job.manufacturing_order_number,
                        "machine_public_id": str(machine.public_id),
                        "machine_code": machine.code,
                        "production_print_public_id": str(print_record.public_id),
                        "is_reprint": is_reprint,
                        "note_present": bool(normalized_note),
                        "source": source,
                    },
                )
                return locked_job, print_record, True
        except ValidationError as exc:
            self._record_rejection(
                job=locked_job or job,
                actor=actor,
                source=source,
                message="; ".join(exc.messages),
            )
            raise

    def _record_rejection(self, *, job, actor, source, message):
        machine = job.assigned_machine
        record_event(
            action="production.print.confirmation_rejected",
            actor=self._authenticated_actor(actor),
            target=job,
            status=AuditLogEntry.Status.FAILURE,
            message=message,
            metadata={
                "customer_public_id": str(job.order.customer.public_id),
                "order_public_id": str(job.order.public_id),
                "production_job_public_id": str(job.public_id),
                "machine_public_id": str(machine.public_id) if machine else None,
                "machine_code": machine.code if machine else "",
                "production_status": job.status,
                "source": source,
            },
        )

    def _normalize_token(self, request_token):
        if not request_token:
            return uuid.uuid4()
        try:
            return uuid.UUID(str(request_token))
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError("Jeton de confirmation invalide.") from exc

    def _require_permissions(self, actor) -> None:
        if not self.access_scope_service.can_access_staff_portal(actor) or any(
            not actor.has_perm(permission) for permission in self.required_permissions
        ):
            raise PermissionDenied

    def _authenticated_actor(self, actor):
        return actor if getattr(actor, "is_authenticated", False) else None
