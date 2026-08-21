import uuid

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.models import (
    ProductionJob,
    ProductionJobMachineAssignment,
    ProductionMachine,
    ProductionPrintRecord,
)
from apps.production.services.machine_assignments import (
    ProductionMachineAssignmentService,
)
from apps.production.services.machine_fleet import MachineFleetService
from apps.production.services.print_tracking import ProductionPrintTrackingService
from apps.production.services.workflow import ProductionWorkflowService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError


def create_user(email, *, permissions=(), is_staff=True, staff_portal=True):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=is_staff,
    )
    permission_codenames = set(permissions)
    if is_staff and staff_portal:
        permission_codenames.add("access_staff_portal")
    for codename in permission_codenames:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


def create_submitted_order(*, actor, name="Machine Fleet Customer"):
    customer = Customer.objects.create(name=name)
    return Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
    )


def create_machine(*, actor, code="DTF-01", name="Atlas"):
    return MachineFleetService().create_machine(
        actor=actor,
        source="test",
        data={
            "code": code,
            "name": name,
            "manufacturer": "Test maker",
            "model_name": "M1",
            "status": ProductionMachine.Status.ACTIVE,
            "max_print_width_cm": "60",
        },
    )


@pytest.mark.django_db
def test_machine_creation_normalizes_code_and_audits_without_sensitive_fields():
    manager = create_user(
        "fleet-manager@example.com",
        permissions=("manage_productionmachine",),
    )

    machine = MachineFleetService().create_machine(
        actor=manager,
        source="test",
        data={
            "code": " dtf-a ",
            "name": "Atlas One",
            "serial_number": "SECRET-SERIAL",
            "notes": "internal maintenance note",
            "status": ProductionMachine.Status.ACTIVE,
        },
    )

    assert machine.code == "DTF-A"
    audit = AuditLogEntry.objects.get(action="production.machine.created")
    assert audit.metadata["machine_public_id"] == str(machine.public_id)
    assert "SECRET-SERIAL" not in str(audit.metadata)
    assert "maintenance note" not in str(audit.metadata)


@pytest.mark.django_db
def test_machine_code_is_unique_case_insensitively():
    manager = create_user(
        "fleet-unique@example.com",
        permissions=("manage_productionmachine",),
    )
    create_machine(actor=manager, code="DTF-ALPHA")

    with pytest.raises(ValidationError, match="déjà utilisé"):
        create_machine(actor=manager, code="dtf-alpha", name="Duplicate")


@pytest.mark.django_db
def test_machine_code_integrity_race_is_translated_and_audited(monkeypatch):
    manager = create_user(
        "fleet-race@example.com",
        permissions=("manage_productionmachine",),
    )
    service = MachineFleetService()
    create_machine(actor=manager, code="DTF-RACE")
    monkeypatch.setattr(service, "_ensure_code_available", lambda **_kwargs: None)

    with pytest.raises(ValidationError, match="déjà utilisé"):
        service.create_machine(
            actor=manager,
            source="test",
            data={"code": "dtf-race", "name": "Concurrent duplicate"},
        )

    assert AuditLogEntry.objects.filter(
        action="production.machine.create_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_machine_mutation_requires_dedicated_permission():
    viewer = create_user("fleet-viewer@example.com")

    with pytest.raises(PermissionDenied):
        create_machine(actor=viewer)

    assert AuditLogEntry.objects.filter(
        action="production.machine.permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_assignment_is_atomic_append_only_and_reassignment_requires_reason():
    manager = create_user(
        "fleet-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    first_machine = create_machine(actor=manager, code="DTF-01", name="Atlas")
    second_machine = create_machine(actor=manager, code="DTF-02", name="Nova")
    service = ProductionMachineAssignmentService()

    job, first_assignment, changed = service.assign(
        order_public_id=order.public_id,
        machine_public_id=first_machine.public_id,
        actor=operator,
        source="test",
    )

    assert changed is True
    assert job.assigned_machine == first_machine
    assert first_assignment.ended_at is None
    assert first_assignment.machine_code_snapshot == "DTF-01"

    with pytest.raises(ValidationError, match="motif"):
        service.assign(
            order_public_id=order.public_id,
            machine_public_id=second_machine.public_id,
            actor=operator,
            source="test",
        )

    job, second_assignment, changed = service.assign(
        order_public_id=order.public_id,
        machine_public_id=second_machine.public_id,
        actor=operator,
        source="test",
        reason="Support plus large",
    )

    first_assignment.refresh_from_db()
    assert changed is True
    assert job.assigned_machine == second_machine
    assert first_assignment.ended_at is not None
    assert second_assignment.previous_machine_code_snapshot == "DTF-01"
    assert (
        ProductionJobMachineAssignment.objects.filter(
            production_job=job,
            ended_at__isnull=True,
        ).count()
        == 1
    )
    assert AuditLogEntry.objects.filter(action="production.machine_assignment.reassigned").exists()


@pytest.mark.django_db
def test_assigning_same_machine_is_idempotent():
    manager = create_user(
        "fleet-idempotent-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-idempotent-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    service = ProductionMachineAssignmentService()
    service.assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )

    _job, _assignment, changed = service.assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )

    assert changed is False
    assert ProductionJobMachineAssignment.objects.count() == 1


@pytest.mark.django_db
def test_inactive_machine_assignment_is_rejected_and_audited():
    manager = create_user(
        "fleet-inactive-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-inactive-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    machine.status = ProductionMachine.Status.MAINTENANCE
    machine.save(update_fields=("status", "updated_at"))

    with pytest.raises(ValidationError, match="disponible"):
        ProductionMachineAssignmentService().assign(
            order_public_id=order.public_id,
            machine_public_id=machine.public_id,
            actor=operator,
            source="test",
        )

    assert not ProductionJobMachineAssignment.objects.exists()
    assert AuditLogEntry.objects.filter(
        action="production.machine_assignment.rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_machine_cannot_leave_service_while_assigned_to_active_job():
    manager = create_user(
        "fleet-status-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-status-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )

    with pytest.raises(ValidationError, match="Réattribuez"):
        MachineFleetService().update_machine(
            machine_public_id=machine.public_id,
            actor=manager,
            source="test",
            data={
                "code": machine.code,
                "name": machine.name,
                "status": ProductionMachine.Status.MAINTENANCE,
            },
        )

    machine.refresh_from_db()
    assert machine.status == ProductionMachine.Status.ACTIVE


@pytest.mark.django_db
def test_machine_cannot_leave_service_while_ready_job_awaits_confirmation():
    manager = create_user(
        "fleet-ready-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-ready-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    job, _assignment, _changed = ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )
    job.status = ProductionJob.Status.READY_TO_SHIP
    job.save(update_fields=("status", "updated_at"))

    with pytest.raises(ValidationError, match="Réattribuez"):
        MachineFleetService().update_machine(
            machine_public_id=machine.public_id,
            actor=manager,
            source="test",
            data={"code": machine.code, "name": machine.name, "status": "maintenance"},
        )


@pytest.mark.django_db
def test_transition_marks_machine_print_started_without_blocking_unassigned_jobs():
    manager = create_user(
        "fleet-workflow-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-workflow-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    job, assignment, _changed = ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )

    ProductionWorkflowService().transition_existing_job(
        production_job=job,
        actor=operator,
        source="test",
        to_status=ProductionJob.Status.IN_PROGRESS,
    )

    assignment.refresh_from_db()
    assert assignment.printing_started_at is not None
    assert AuditLogEntry.objects.filter(action="production.machine_print_started").exists()

    unassigned_order = create_submitted_order(actor=operator, name="Legacy compatible")
    unassigned_job = ProductionWorkflowService().get_or_create_for_order(order=unassigned_order)
    ProductionWorkflowService().transition_existing_job(
        production_job=unassigned_job,
        actor=operator,
        source="test",
        to_status=ProductionJob.Status.IN_PROGRESS,
    )
    unassigned_job.refresh_from_db()
    assert unassigned_job.status == ProductionJob.Status.IN_PROGRESS


@pytest.mark.django_db
def test_print_confirmation_is_idempotent_and_reprint_requires_note():
    manager = create_user(
        "fleet-print-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-print-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
            "confirm_productionprint",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    job, _assignment, _changed = ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )
    ProductionWorkflowService().transition_existing_job(
        production_job=job,
        actor=operator,
        source="test",
        to_status=ProductionJob.Status.IN_PROGRESS,
    )
    service = ProductionPrintTrackingService()
    token = uuid.uuid4()

    _job, first_print, created = service.confirm_print(
        order_public_id=order.public_id,
        actor=operator,
        source="test",
        request_token=token,
    )
    _job, same_print, duplicate_created = service.confirm_print(
        order_public_id=order.public_id,
        actor=operator,
        source="test",
        request_token=token,
    )

    assert created is True
    assert duplicate_created is False
    assert same_print == first_print
    assert ProductionPrintRecord.objects.count() == 1

    with pytest.raises(ValidationError, match="réimpression"):
        service.confirm_print(
            order_public_id=order.public_id,
            actor=operator,
            source="test",
        )

    _job, reprint, created = service.confirm_print(
        order_public_id=order.public_id,
        actor=operator,
        source="test",
        note="Relance après contrôle qualité",
    )
    assert created is True
    assert reprint.machine_code_snapshot == machine.code
    assert ProductionPrintRecord.objects.count() == 2
    assert AuditLogEntry.objects.filter(action="production.print.reconfirmed").exists()


@pytest.mark.django_db
def test_print_idempotency_token_cannot_be_reused_across_orders():
    manager = create_user(
        "fleet-token-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-token-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
            "confirm_productionprint",
        ),
    )
    machine = create_machine(actor=manager)
    service = ProductionPrintTrackingService()
    token = uuid.uuid4()

    for index in range(2):
        order = create_submitted_order(actor=operator, name=f"Token customer {index}")
        job, _assignment, _changed = ProductionMachineAssignmentService().assign(
            order_public_id=order.public_id,
            machine_public_id=machine.public_id,
            actor=operator,
            source="test",
        )
        ProductionWorkflowService().transition_existing_job(
            production_job=job,
            actor=operator,
            source="test",
            to_status=ProductionJob.Status.IN_PROGRESS,
        )
        if index == 0:
            service.confirm_print(
                order_public_id=order.public_id,
                actor=operator,
                source="test",
                request_token=token,
            )
            continue

        with pytest.raises(ValidationError, match="autre dossier"):
            service.confirm_print(
                order_public_id=order.public_id,
                actor=operator,
                source="test",
                request_token=token,
            )

    assert ProductionPrintRecord.objects.count() == 1
    assert AuditLogEntry.objects.filter(
        action="production.print.confirmation_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_print_integrity_race_is_translated_and_audited(monkeypatch):
    manager = create_user(
        "fleet-print-race-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-print-race-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
            "confirm_productionprint",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager)
    job, _assignment, _changed = ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )
    ProductionWorkflowService().transition_existing_job(
        production_job=job,
        actor=operator,
        source="test",
        to_status=ProductionJob.Status.IN_PROGRESS,
    )

    def raise_integrity_error(**_kwargs):
        raise IntegrityError("simulated token race")

    monkeypatch.setattr(ProductionPrintRecord.objects, "create", raise_integrity_error)

    with pytest.raises(ValidationError, match="Conflit de confirmation"):
        ProductionPrintTrackingService().confirm_print(
            order_public_id=order.public_id,
            actor=operator,
            source="test",
            request_token=uuid.uuid4(),
        )

    assert AuditLogEntry.objects.filter(
        action="production.print.confirmation_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_history_snapshots_survive_machine_rename_and_prevent_deletion():
    manager = create_user(
        "fleet-history-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    operator = create_user(
        "fleet-history-operator@example.com",
        permissions=(
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
        ),
    )
    order = create_submitted_order(actor=operator)
    machine = create_machine(actor=manager, code="DTF-OLD", name="Old Name")
    _job, assignment, _changed = ProductionMachineAssignmentService().assign(
        order_public_id=order.public_id,
        machine_public_id=machine.public_id,
        actor=operator,
        source="test",
    )

    machine.code = "DTF-NEW"
    machine.name = "New Name"
    machine.save(update_fields=("code", "name", "updated_at"))
    assignment.refresh_from_db()

    assert assignment.machine_code_snapshot == "DTF-OLD"
    assert assignment.machine_name_snapshot == "Old Name"
    with pytest.raises(ProtectedError):
        machine.delete()


@pytest.mark.django_db
def test_assignment_permission_is_enforced_before_mutation():
    manager = create_user(
        "fleet-boundary-admin@example.com",
        permissions=("manage_productionmachine",),
    )
    viewer = create_user(
        "fleet-boundary-viewer@example.com",
        permissions=("view_order", "view_productionjob"),
    )
    order = create_submitted_order(actor=viewer)
    machine = create_machine(actor=manager)

    with pytest.raises(PermissionDenied):
        ProductionMachineAssignmentService().assign(
            order_public_id=order.public_id,
            machine_public_id=machine.public_id,
            actor=viewer,
            source="test",
        )

    assert not ProductionJobMachineAssignment.objects.exists()


@pytest.mark.django_db
def test_non_staff_with_domain_permissions_cannot_call_machine_services():
    permissions = (
        "access_staff_portal",
        "view_productionmachine",
        "manage_productionmachine",
        "view_order",
        "view_productionjob",
        "assign_productionmachine",
        "confirm_productionprint",
    )
    attacker = create_user(
        "fleet-client-with-perms@example.com",
        permissions=permissions,
        is_staff=False,
    )
    manager = create_user(
        "fleet-defense-manager@example.com",
        permissions=("manage_productionmachine",),
    )
    order = create_submitted_order(actor=manager)
    machine = create_machine(actor=manager)

    with pytest.raises(PermissionDenied):
        MachineFleetService().list_machines(actor=attacker)
    with pytest.raises(PermissionDenied):
        create_machine(actor=attacker, code="DTF-FORGED")
    with pytest.raises(PermissionDenied):
        ProductionMachineAssignmentService().assign(
            order_public_id=order.public_id,
            machine_public_id=machine.public_id,
            actor=attacker,
            source="test",
        )
    with pytest.raises(PermissionDenied):
        ProductionPrintTrackingService().confirm_print(
            order_public_id=order.public_id,
            actor=attacker,
            source="test",
        )

    assert not ProductionJobMachineAssignment.objects.exists()
