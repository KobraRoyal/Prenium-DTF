from unittest.mock import patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.core.public_refs import short_public_ref
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob, ProductionJobScanLog, ProductionJobTransition
from apps.production.services.scans import ProductionScanService
from apps.production.services.workflow import ProductionWorkflowService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


def create_customer_scope(email: str, customer_name: str):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name)
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    return user, customer, membership


def create_order(customer, actor):
    return Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
    )


@pytest.mark.django_db
def test_transition_job_updates_status_creates_history_and_audit():
    service = ProductionWorkflowService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)

    job = service.get_or_create_for_order(order=order)

    assert job.status == ProductionJob.Status.QUEUED
    assert job.manufacturing_order_number.startswith("OF-")

    _order, updated_job, transition = service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=staff_user,
        source="test",
        reason="Launch production",
    )

    assert updated_job.status == ProductionJob.Status.IN_PROGRESS
    assert updated_job.started_at is not None
    assert updated_job.last_transition_at is not None
    assert updated_job.last_transition_by == staff_user
    assert updated_job.last_transition_note == "Launch production"
    assert transition.from_status == ProductionJob.Status.QUEUED
    assert transition.to_status == ProductionJob.Status.IN_PROGRESS
    assert transition.changed_by == staff_user
    assert transition.reason == "Launch production"
    assert ProductionJobTransition.objects.filter(production_job=updated_job).count() == 1
    assert AuditLogEntry.objects.filter(
        action="production.status_changed",
        target_public_id=updated_job.public_id,
    ).exists()


@pytest.mark.django_db
def test_lifecycle_emails_are_scheduled_once_at_real_production_milestones():
    service = ProductionWorkflowService()
    actor, customer, _membership = create_customer_scope("notify@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-notify@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)

    with (
        patch(
            "apps.notifications.services.transactional.schedule_order_processing_email"
        ) as processing_schedule,
        patch(
            "apps.notifications.services.transactional.schedule_order_ready_to_ship_email"
        ) as ready_schedule,
    ):
        service.transition_job(
            order_public_id=order.public_id,
            to_status=ProductionJob.Status.IN_PROGRESS,
            actor=staff_user,
            source="test",
        )
        service.transition_job(
            order_public_id=order.public_id,
            to_status=ProductionJob.Status.BLOCKED,
            actor=staff_user,
            source="test",
        )
        service.transition_job(
            order_public_id=order.public_id,
            to_status=ProductionJob.Status.IN_PROGRESS,
            actor=staff_user,
            source="test",
        )
        service.transition_job(
            order_public_id=order.public_id,
            to_status=ProductionJob.Status.READY_TO_SHIP,
            actor=staff_user,
            source="test",
        )

    processing_schedule.assert_called_once_with(order_public_id=order.public_id)
    ready_schedule.assert_called_once_with(order_public_id=order.public_id)


@pytest.mark.django_db
def test_get_or_create_for_order_generates_unique_scan_identifier():
    service = ProductionWorkflowService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order_one = create_order(customer, actor)
    order_two = create_order(customer, actor)

    job_one = service.get_or_create_for_order(order=order_one)
    job_two = service.get_or_create_for_order(order=order_two)

    assert job_one.scan_identifier
    assert job_two.scan_identifier
    assert job_one.scan_identifier != job_two.scan_identifier
    assert ProductionJob.objects.filter(scan_identifier=job_one.scan_identifier).count() == 1
    assert ProductionJob.objects.filter(scan_identifier=job_two.scan_identifier).count() == 1


@pytest.mark.django_db
def test_invalid_transition_is_refused_and_failure_audited():
    service = ProductionWorkflowService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    job = service.get_or_create_for_order(order=order)

    with pytest.raises(ValidationError, match="Transition not allowed from the current status."):
        service.transition_job(
            order_public_id=order.public_id,
            to_status=ProductionJob.Status.COMPLETED,
            actor=staff_user,
            source="test",
        )

    job.refresh_from_db()
    assert job.status == ProductionJob.Status.QUEUED
    assert ProductionJobTransition.objects.filter(production_job=job).count() == 0
    assert AuditLogEntry.objects.filter(
        action="production.transition_rejected",
        target_public_id=job.public_id,
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_transition_existing_job_reloads_state_under_lock_before_validation():
    service = ProductionWorkflowService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    stale_job = service.get_or_create_for_order(order=order)

    _order, updated_job, _transition = service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=staff_user,
        source="test",
        reason="Launch production",
    )

    assert updated_job.status == ProductionJob.Status.IN_PROGRESS
    with pytest.raises(ValidationError, match="Transition not allowed from the current status."):
        service.transition_existing_job(
            production_job=stale_job,
            actor=staff_user,
            source="test",
            to_status=ProductionJob.Status.IN_PROGRESS,
            reason="Duplicate launch",
        )

    updated_job.refresh_from_db()
    assert updated_job.status == ProductionJob.Status.IN_PROGRESS
    assert ProductionJobTransition.objects.filter(production_job=updated_job).count() == 1


def test_allowed_target_statuses_match_central_workflow_order():
    service = ProductionWorkflowService()

    assert service.allowed_target_statuses(
        current_status=ProductionJob.Status.QUEUED
    ) == [ProductionJob.Status.IN_PROGRESS, ProductionJob.Status.BLOCKED]
    assert service.allowed_target_statuses(
        current_status=ProductionJob.Status.READY_TO_SHIP
    ) == [ProductionJob.Status.COMPLETED]
    assert service.allowed_target_statuses(
        current_status=ProductionJob.Status.COMPLETED
    ) == []


@pytest.mark.django_db
def test_production_job_scan_matches_manufacturing_order_reference():
    service = ProductionWorkflowService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)

    job = service.get_or_create_for_order(order=order)
    order.refresh_from_db()
    document = service.build_manufacturing_order(order=order, production_job=job)

    assert job.scan_identifier == job.manufacturing_order_number
    assert job.scan_identifier.startswith("OF-")
    assert ProductionJob.objects.filter(scan_identifier=job.scan_identifier).count() == 1
    assert document["order_summary"]["reference"] == short_public_ref(order.public_id).upper()
    assert document["order_summary"]["reference"] != job.manufacturing_order_number


@pytest.mark.django_db
def test_scan_service_resolves_job_and_creates_log():
    workflow_service = ProductionWorkflowService()
    scan_service = ProductionScanService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-scan@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    job = workflow_service.get_or_create_for_order(order=order)

    resolved_job = scan_service.resolve_scan(
        scan_identifier=job.scan_identifier,
        actor=staff_user,
        source="test_scan_api",
    )

    assert resolved_job == job
    scan_log = ProductionJobScanLog.objects.get(
        production_job=job,
        action=ProductionJobScanLog.Action.RESOLVE,
    )
    assert scan_log.outcome == ProductionJobScanLog.Outcome.RESOLVED
    assert scan_log.scan_identifier == job.scan_identifier
    assert AuditLogEntry.objects.filter(
        action="production.scan_resolved",
        target_public_id=job.public_id,
    ).exists()


@pytest.mark.django_db
def test_scan_service_unknown_identifier_returns_none_and_logs_failure():
    scan_service = ProductionScanService()
    staff_user = get_user_model().objects.create_user(
        email="staff-scan@example.com",
        password="pass",
        is_staff=True,
    )

    resolved_job = scan_service.resolve_scan(
        scan_identifier="pjscan-missing",
        actor=staff_user,
        source="test_scan_api",
    )

    assert resolved_job is None
    scan_log = ProductionJobScanLog.objects.get(action=ProductionJobScanLog.Action.RESOLVE)
    assert scan_log.outcome == ProductionJobScanLog.Outcome.NOT_FOUND
    assert scan_log.scan_identifier == "PJSCAN-MISSING"
    assert AuditLogEntry.objects.filter(
        action="production.scan_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_scan_transition_reuses_workflow_and_creates_transition_log():
    workflow_service = ProductionWorkflowService()
    scan_service = ProductionScanService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-scan@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    job = workflow_service.get_or_create_for_order(order=order)

    updated_job, transition = scan_service.transition_by_scan(
        scan_identifier=job.scan_identifier,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=staff_user,
        source="test_scan_api",
        reason="Scan start",
    )

    assert updated_job.status == ProductionJob.Status.IN_PROGRESS
    assert transition.to_status == ProductionJob.Status.IN_PROGRESS
    assert ProductionJobScanLog.objects.filter(
        production_job=job,
        action=ProductionJobScanLog.Action.TRANSITION,
        outcome=ProductionJobScanLog.Outcome.TRANSITIONED,
        requested_status=ProductionJob.Status.IN_PROGRESS,
    ).exists()


@pytest.mark.django_db
def test_scan_transition_invalid_status_is_refused_and_logged():
    workflow_service = ProductionWorkflowService()
    scan_service = ProductionScanService()
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-scan@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    job = workflow_service.get_or_create_for_order(order=order)

    with pytest.raises(ValidationError, match="Transition not allowed from the current status."):
        scan_service.transition_by_scan(
            scan_identifier=job.scan_identifier,
            to_status=ProductionJob.Status.COMPLETED,
            actor=staff_user,
            source="test_scan_api",
        )

    assert ProductionJobScanLog.objects.filter(
        production_job=job,
        action=ProductionJobScanLog.Action.TRANSITION,
        outcome=ProductionJobScanLog.Outcome.REJECTED,
        requested_status=ProductionJob.Status.COMPLETED,
    ).exists()
