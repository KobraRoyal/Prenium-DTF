from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.orders.models import Order
from apps.production.models import (
    ProductionJob,
    ProductionJobMachineAssignment,
    ProductionMachine,
)
from apps.production.services.workflow import ProductionWorkflowService


class ProductionMachineAssignmentService:
    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
        "production.assign_productionmachine",
    )
    mutable_statuses = {
        ProductionJob.Status.QUEUED,
        ProductionJob.Status.IN_PROGRESS,
        ProductionJob.Status.BLOCKED,
    }

    def __init__(self):
        self.access_scope_service = AccessScopeService()

    def assign(
        self,
        *,
        order_public_id,
        machine_public_id,
        actor,
        source: str,
        reason: str = "",
    ) -> tuple[ProductionJob, ProductionJobMachineAssignment, bool]:
        try:
            self._require_permissions(actor)
        except PermissionDenied:
            record_event(
                action="production.machine_assignment.rejected",
                actor=self._authenticated_actor(actor),
                status=AuditLogEntry.Status.FAILURE,
                message="Permission denied.",
                metadata={"source": source},
            )
            raise
        normalized_reason = str(reason).strip()[:255]
        order = Order.objects.filter(public_id=order_public_id).first()
        if order is None:
            message = "Dossier Atelier introuvable."
            record_event(
                action="production.machine_assignment.rejected",
                actor=self._authenticated_actor(actor),
                status=AuditLogEntry.Status.FAILURE,
                message=message,
                metadata={"source": source, "reason": "object_not_found"},
            )
            raise ValidationError(message)
        job = ProductionWorkflowService().get_or_create_for_order(order=order)

        locked_job = None
        machine = None
        try:
            with transaction.atomic():
                locked_job = (
                    ProductionJob.objects.select_for_update(of=("self",))
                    .select_related("order", "order__customer", "assigned_machine")
                    .get(pk=job.pk)
                )
                machine = (
                    ProductionMachine.objects.select_for_update()
                    .filter(public_id=machine_public_id)
                    .first()
                )
                if machine is None:
                    raise ValidationError("Imprimante introuvable.")
                if machine.status != ProductionMachine.Status.ACTIVE:
                    raise ValidationError("Cette imprimante n’est pas disponible.")
                if locked_job.order.status == Order.Status.CANCELLED:
                    raise ValidationError("Une commande annulée ne peut pas être attribuée.")
                if locked_job.status not in self.mutable_statuses:
                    raise ValidationError("Ce dossier ne peut plus être réattribué.")

                current_assignment = (
                    ProductionJobMachineAssignment.objects.select_for_update()
                    .filter(production_job=locked_job, ended_at__isnull=True)
                    .select_related("machine")
                    .first()
                )
                if locked_job.assigned_machine_id == machine.pk:
                    if current_assignment is None:
                        current_assignment = self._create_assignment(
                            job=locked_job,
                            machine=machine,
                            previous_machine=None,
                            actor=actor,
                            source=source,
                            reason=normalized_reason,
                        )
                    return locked_job, current_assignment, False

                previous_machine = locked_job.assigned_machine
                if previous_machine is not None and not normalized_reason:
                    raise ValidationError("Un motif est obligatoire pour réattribuer ce dossier.")

                now = timezone.now()
                if current_assignment is not None:
                    current_assignment.ended_at = now
                    current_assignment.ended_by = self._authenticated_actor(actor)
                    current_assignment.save(
                        update_fields=("ended_at", "ended_by", "updated_at")
                    )

                assignment = self._create_assignment(
                    job=locked_job,
                    machine=machine,
                    previous_machine=previous_machine,
                    actor=actor,
                    source=source,
                    reason=normalized_reason,
                    printing_started_at=(
                        now if locked_job.status == ProductionJob.Status.IN_PROGRESS else None
                    ),
                )
                locked_job.assigned_machine = machine
                locked_job.machine_assigned_at = now
                locked_job.machine_assigned_by = self._authenticated_actor(actor)
                locked_job.save(
                    update_fields=(
                        "assigned_machine",
                        "machine_assigned_at",
                        "machine_assigned_by",
                        "updated_at",
                    )
                )

                action = (
                    "production.machine_assignment.reassigned"
                    if previous_machine is not None
                    else "production.machine_assignment.created"
                )
                record_event(
                    action=action,
                    actor=self._authenticated_actor(actor),
                    target=assignment,
                    metadata=self._audit_metadata(
                        job=locked_job,
                        machine=machine,
                        previous_machine=previous_machine,
                        source=source,
                        reason_present=bool(normalized_reason),
                    ),
                )
                if locked_job.status == ProductionJob.Status.IN_PROGRESS:
                    self.record_print_started(
                        job=locked_job,
                        assignment=assignment,
                        actor=actor,
                        source=source,
                    )
                return locked_job, assignment, True
        except ValidationError as exc:
            self._record_rejection(
                job=locked_job or job,
                machine=machine,
                machine_public_id=machine_public_id,
                actor=actor,
                source=source,
                message="; ".join(exc.messages),
            )
            raise

    def mark_print_started_for_transition(
        self,
        *,
        job: ProductionJob,
        actor,
        source: str,
        now,
    ) -> ProductionJobMachineAssignment | None:
        if job.assigned_machine_id is None:
            return None
        assignment = (
            ProductionJobMachineAssignment.objects.select_for_update()
            .filter(production_job=job, ended_at__isnull=True)
            .select_related("machine")
            .first()
        )
        if assignment is None:
            return None
        if assignment.printing_started_at is None:
            assignment.printing_started_at = now
            assignment.save(update_fields=("printing_started_at", "updated_at"))
            self.record_print_started(
                job=job,
                assignment=assignment,
                actor=actor,
                source=source,
            )
        return assignment

    def record_print_started(self, *, job, assignment, actor, source: str) -> None:
        record_event(
            action="production.machine_print_started",
            actor=self._authenticated_actor(actor),
            target=assignment,
            metadata=self._audit_metadata(
                job=job,
                machine=assignment.machine,
                previous_machine=assignment.previous_machine,
                source=source,
                reason_present=bool(assignment.reason),
            ),
        )

    def _create_assignment(
        self,
        *,
        job,
        machine,
        previous_machine,
        actor,
        source,
        reason,
        printing_started_at=None,
    ):
        return ProductionJobMachineAssignment.objects.create(
            production_job=job,
            machine=machine,
            previous_machine=previous_machine,
            assigned_by=self._authenticated_actor(actor),
            source=source,
            reason=reason,
            machine_public_id_snapshot=machine.public_id,
            machine_code_snapshot=machine.code,
            machine_name_snapshot=machine.name,
            previous_machine_public_id_snapshot=(
                previous_machine.public_id if previous_machine is not None else None
            ),
            previous_machine_code_snapshot=(
                previous_machine.code if previous_machine is not None else ""
            ),
            previous_machine_name_snapshot=(
                previous_machine.name if previous_machine is not None else ""
            ),
            printing_started_at=printing_started_at,
        )

    def _audit_metadata(
        self,
        *,
        job,
        machine,
        previous_machine,
        source,
        reason_present,
    ):
        return {
            "customer_public_id": str(job.order.customer.public_id),
            "order_public_id": str(job.order.public_id),
            "production_job_public_id": str(job.public_id),
            "manufacturing_order_number": job.manufacturing_order_number,
            "machine_public_id": str(machine.public_id),
            "machine_code": machine.code,
            "previous_machine_public_id": (
                str(previous_machine.public_id) if previous_machine is not None else None
            ),
            "previous_machine_code": previous_machine.code if previous_machine else "",
            "production_status": job.status,
            "reason_present": reason_present,
            "source": source,
        }

    def _record_rejection(
        self,
        *,
        job,
        machine,
        machine_public_id,
        actor,
        source,
        message,
    ):
        metadata = {
            "order_public_id": str(job.order.public_id),
            "customer_public_id": str(job.order.customer.public_id),
            "production_job_public_id": str(job.public_id),
            "machine_public_id": str(machine.public_id if machine else machine_public_id),
            "machine_code": machine.code if machine else "",
            "source": source,
        }
        record_event(
            action="production.machine_assignment.rejected",
            actor=self._authenticated_actor(actor),
            target=job,
            status=AuditLogEntry.Status.FAILURE,
            message=message,
            metadata=metadata,
        )

    def _require_permissions(self, actor) -> None:
        if not self.access_scope_service.can_access_staff_portal(actor) or any(
            not actor.has_perm(permission) for permission in self.required_permissions
        ):
            raise PermissionDenied

    def _authenticated_actor(self, actor):
        return actor if getattr(actor, "is_authenticated", False) else None
