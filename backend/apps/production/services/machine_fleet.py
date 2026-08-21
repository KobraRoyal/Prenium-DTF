from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.production.models import ProductionJob, ProductionMachine


class MachineFleetService:
    view_permission = "production.view_productionmachine"
    manage_permission = "production.manage_productionmachine"
    active_job_statuses = {
        ProductionJob.Status.QUEUED,
        ProductionJob.Status.IN_PROGRESS,
        ProductionJob.Status.BLOCKED,
        ProductionJob.Status.READY_TO_SHIP,
    }

    def __init__(self):
        self.access_scope_service = AccessScopeService()

    def list_machines(self, *, actor):
        self._require_read_permission(actor)
        return ProductionMachine.objects.annotate(
            active_job_count=Count(
                "assigned_jobs",
                filter=Q(assigned_jobs__status__in=self.active_job_statuses),
                distinct=True,
            ),
            print_count=Count("print_records", distinct=True),
        ).select_related("status_changed_by")

    def get_machine(self, *, machine_public_id, actor):
        return (
            self.list_machines(actor=actor)
            .filter(public_id=machine_public_id)
            .first()
        )

    def create_machine(self, *, actor, source: str, data: dict) -> ProductionMachine:
        try:
            self._require_manage_permission(actor)
        except PermissionDenied:
            self._record_permission_rejection(actor=actor, source=source)
            raise
        cleaned = {}
        try:
            cleaned = self._clean_machine_data(data)
            with transaction.atomic():
                self._ensure_code_available(code=cleaned["code"])
                machine = ProductionMachine.objects.create(
                    **cleaned,
                    status_changed_at=timezone.now(),
                    status_changed_by=self._authenticated_actor(actor),
                )
                record_event(
                    action="production.machine.created",
                    actor=self._authenticated_actor(actor),
                    target=machine,
                    metadata=self._machine_audit_metadata(machine=machine, source=source),
                )
                return machine
        except IntegrityError as exc:
            validation_error = ValidationError("Ce code machine est déjà utilisé.")
            self._record_rejection(
                actor=actor,
                source=source,
                action="production.machine.create_rejected",
                message=self._validation_message(validation_error),
                code=cleaned.get("code", ""),
            )
            raise validation_error from exc
        except ValidationError as exc:
            self._record_rejection(
                actor=actor,
                source=source,
                action="production.machine.create_rejected",
                message=self._validation_message(exc),
                code=cleaned.get("code", ""),
            )
            raise

    def update_machine(
        self,
        *,
        machine_public_id,
        actor,
        source: str,
        data: dict,
    ) -> ProductionMachine:
        try:
            self._require_manage_permission(actor)
        except PermissionDenied:
            self._record_permission_rejection(actor=actor, source=source)
            raise
        cleaned = {}
        machine = None
        try:
            cleaned = self._clean_machine_data(data)
            with transaction.atomic():
                machine = (
                    ProductionMachine.objects.select_for_update()
                    .filter(public_id=machine_public_id)
                    .first()
                )
                if machine is None:
                    raise ValidationError("Imprimante introuvable.")
                self._ensure_code_available(code=cleaned["code"], exclude_pk=machine.pk)
                previous_status = machine.status
                next_status = cleaned["status"]
                if (
                    previous_status == ProductionMachine.Status.ACTIVE
                    and next_status != previous_status
                ):
                    self._ensure_machine_can_leave_service(machine=machine)

                for field_name, value in cleaned.items():
                    setattr(machine, field_name, value)
                if previous_status != next_status:
                    machine.status_changed_at = timezone.now()
                    machine.status_changed_by = self._authenticated_actor(actor)
                machine.save()

                action = (
                    "production.machine.status_changed"
                    if previous_status != next_status
                    else "production.machine.updated"
                )
                metadata = self._machine_audit_metadata(machine=machine, source=source)
                metadata.update(
                    {
                        "from_status": previous_status,
                        "to_status": next_status,
                    }
                )
                record_event(
                    action=action,
                    actor=self._authenticated_actor(actor),
                    target=machine,
                    metadata=metadata,
                )
                return machine
        except IntegrityError as exc:
            validation_error = ValidationError("Ce code machine est déjà utilisé.")
            self._record_rejection(
                actor=actor,
                source=source,
                action="production.machine.update_rejected",
                message=self._validation_message(validation_error),
                machine=machine,
                code=cleaned.get("code", ""),
            )
            raise validation_error from exc
        except ValidationError as exc:
            self._record_rejection(
                actor=actor,
                source=source,
                action="production.machine.update_rejected",
                message=self._validation_message(exc),
                machine=machine,
                code=cleaned.get("code", ""),
            )
            raise

    def fleet_summary(self, *, actor) -> dict[str, int]:
        self._require_read_permission(actor)
        counts = {
            row["status"]: row["count"]
            for row in ProductionMachine.objects.values("status").annotate(count=Count("pk"))
        }
        return {
            "total": sum(counts.values()),
            "active": counts.get(ProductionMachine.Status.ACTIVE, 0),
            "maintenance": counts.get(ProductionMachine.Status.MAINTENANCE, 0),
            "retired": counts.get(ProductionMachine.Status.RETIRED, 0),
        }

    def _clean_machine_data(self, data: dict) -> dict:
        code = str(data.get("code", "")).strip().upper()
        name = str(data.get("name", "")).strip()
        status = str(data.get("status", ProductionMachine.Status.ACTIVE)).strip()
        if not code:
            raise ValidationError("Le code machine est obligatoire.")
        if not name:
            raise ValidationError("Le nom de la machine est obligatoire.")
        if status not in ProductionMachine.Status.values:
            raise ValidationError("Le statut machine est invalide.")

        width_raw = str(data.get("max_print_width_cm", "")).strip()
        width = None
        if width_raw:
            try:
                width = Decimal(width_raw.replace(",", "."))
            except InvalidOperation as exc:
                raise ValidationError("La laize maximale doit être un nombre.") from exc
            if width <= 0 or width > 999:
                raise ValidationError("La laize maximale doit être comprise entre 0 et 999 cm.")

        return {
            "code": code[:32],
            "name": name[:120],
            "manufacturer": str(data.get("manufacturer", "")).strip()[:80],
            "model_name": str(data.get("model_name", "")).strip()[:120],
            "serial_number": str(data.get("serial_number", "")).strip()[:120],
            "location": str(data.get("location", "")).strip()[:120],
            "max_print_width_cm": width,
            "status": status,
            "notes": str(data.get("notes", "")).strip()[:2000],
        }

    def _ensure_code_available(self, *, code: str, exclude_pk=None) -> None:
        queryset = ProductionMachine.objects.filter(code__iexact=code)
        if exclude_pk is not None:
            queryset = queryset.exclude(pk=exclude_pk)
        if queryset.exists():
            raise ValidationError("Ce code machine est déjà utilisé.")

    def _ensure_machine_can_leave_service(self, *, machine: ProductionMachine) -> None:
        if ProductionJob.objects.filter(
            assigned_machine=machine,
            status__in=self.active_job_statuses,
        ).exists():
            raise ValidationError(
                "Réattribuez les dossiers actifs avant de retirer cette machine du service."
            )

    def _machine_audit_metadata(self, *, machine: ProductionMachine, source: str) -> dict:
        return {
            "machine_public_id": str(machine.public_id),
            "machine_code": machine.code,
            "machine_status": machine.status,
            "source": source,
        }

    def _record_rejection(
        self,
        *,
        actor,
        source: str,
        action: str,
        message: str,
        machine: ProductionMachine | None = None,
        code: str = "",
    ) -> None:
        metadata = {"source": source, "machine_code": code}
        if machine is not None:
            metadata.update(self._machine_audit_metadata(machine=machine, source=source))
        record_event(
            action=action,
            actor=self._authenticated_actor(actor),
            target=machine,
            status=AuditLogEntry.Status.FAILURE,
            message=message,
            metadata=metadata,
        )

    def _require_manage_permission(self, actor) -> None:
        if not self.access_scope_service.can_access_staff_portal(
            actor
        ) or not actor.has_perm(self.manage_permission):
            raise PermissionDenied

    def _require_read_permission(self, actor) -> None:
        if not self.access_scope_service.can_access_staff_portal(actor) or not (
            actor.has_perm(self.view_permission) or actor.has_perm(self.manage_permission)
        ):
            raise PermissionDenied

    def _record_permission_rejection(self, *, actor, source: str) -> None:
        record_event(
            action="production.machine.permission_rejected",
            actor=self._authenticated_actor(actor),
            status=AuditLogEntry.Status.FAILURE,
            message="Permission denied.",
            metadata={"source": source},
        )

    def _authenticated_actor(self, actor):
        return actor if getattr(actor, "is_authenticated", False) else None

    def _validation_message(self, exc: ValidationError) -> str:
        return "; ".join(exc.messages)
