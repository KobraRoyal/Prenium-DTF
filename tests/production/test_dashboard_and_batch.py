from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.accounts.models import StaffMembership
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Payment
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.models import (
    ProductionJob,
    ProductionJobMachineAssignment,
    ProductionMachine,
    ProductionPrintRecord,
)
from apps.production.services.dashboard import AtelierDashboardService
from apps.production.services.manufacturing_order_batch import (
    ManufacturingOrderBatchService,
)
from apps.production.services.manufacturing_order_pdf import (
    render_manufacturing_order_pdf_bytes,
)
from apps.production.services.staff_order_list_filters import StaffOrderListFilterService
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUpload, OrderUploadDriveSync, OrderUploadReview
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone


def create_order(*, customer, actor, status=Order.Status.SUBMITTED):
    order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=status,
        billing_mode=Order.BillingMode.DEFERRED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
    )
    if status == Order.Status.SUBMITTED:
        ProductionWorkflowService().get_or_create_for_order(order=order)
    return order


def add_upload(*, order, actor, filename: str, approved: bool):
    upload = OrderUpload.objects.create(
        order=order,
        uploaded_by=actor,
        file=f"orders/test/{filename}",
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=128,
    )
    if approved:
        OrderUploadReview.objects.create(
            order_upload=upload,
            status=OrderUploadReview.Status.APPROVED,
            reviewed_by=actor,
        )
    return upload


def mark_of_issued(order):
    order.production_job.of_document_issued_at = timezone.now()
    order.production_job.save(update_fields=["of_document_issued_at", "updated_at"])


def create_staff_client(*, email: str, permissions: list[str]):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    user.user_permissions.add(
        *(Permission.objects.get(codename=codename) for codename in permissions)
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    return user, client


@pytest.mark.django_db
def test_atelier_dashboard_shows_only_unissued_orders():
    actor = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Atelier Client")
    unissued = create_order(customer=customer, actor=actor)
    issued = create_order(customer=customer, actor=actor)
    completed = create_order(customer=customer, actor=actor)
    add_upload(order=unissued, actor=actor, filename="open.pdf", approved=False)
    add_upload(order=issued, actor=actor, filename="issued.pdf", approved=True)
    add_upload(order=completed, actor=actor, filename="done.pdf", approved=True)
    mark_of_issued(issued)
    completed.production_job.status = ProductionJob.Status.COMPLETED
    completed.production_job.save(update_fields=["status", "updated_at"])

    dashboard = AtelierDashboardService().build_dashboard()

    assert [row["order"].public_id for row in dashboard["rows"]] == [unissued.public_id]
    assert dashboard["unprinted_of_total"] == 1


@pytest.mark.django_db
def test_immediate_order_enters_atelier_and_can_print_only_after_capture():
    actor = get_user_model().objects.create_user(email="payment-gate@example.com", password="pass")
    first_customer = Customer.objects.create(name="Awaiting payment")
    other_customer = Customer.objects.create(name="Other tenant")
    unpaid = create_order(customer=first_customer, actor=actor)
    other = create_order(customer=other_customer, actor=actor)
    unpaid.billing_mode = other.billing_mode = Order.BillingMode.IMMEDIATE
    unpaid.save(update_fields=["billing_mode", "updated_at"])
    other.save(update_fields=["billing_mode", "updated_at"])
    batch = ManufacturingOrderBatchService()
    workflow = ProductionWorkflowService()

    assert batch.count_unissued_orders() == 0
    assert StaffOrderListFilterService().count_by_queue(Order.objects.all())["unprinted"] == 0
    assert (
        StaffOrderListFilterService().count_by_status(Order.objects.all())[
            ProductionJob.Status.QUEUED
        ]
        == 0
    )
    assert AtelierDashboardService().build_dashboard()["rows"] == []
    assert workflow.get_staff_job_for_document(order_public_id=unpaid.public_id) == (None, None)
    with pytest.raises(ValidationError):
        batch.resolve_orders(order_public_ids=[str(unpaid.public_id)], mode="selected")
    with pytest.raises(ValidationError):
        batch.mark_of_documents_issued(orders=[unpaid], actor=actor, source="test")
    with pytest.raises(ValidationError):
        render_manufacturing_order_pdf_bytes(order=unpaid, production_job=unpaid.production_job)
    unpaid.production_job.refresh_from_db()
    assert unpaid.production_job.of_document_issued_at is None

    Payment.objects.create(
        order=unpaid,
        amount="42.00",
        currency="EUR",
        status=Payment.Status.CAPTURED,
        provider=Payment.Provider.STRIPE,
    )
    assert [order.public_id for order in batch.list_unissued_orders()] == [unpaid.public_id]
    assert StaffOrderListFilterService().count_by_queue(Order.objects.all())["unprinted"] == 1
    assert (
        StaffOrderListFilterService().count_by_status(Order.objects.all())[
            ProductionJob.Status.QUEUED
        ]
        == 1
    )
    assert [
        row["order"].public_id for row in AtelierDashboardService().build_dashboard()["rows"]
    ] == [unpaid.public_id]
    assert workflow.get_staff_job_for_document(order_public_id=unpaid.public_id)[1] is not None
    assert workflow.get_staff_job_for_document(order_public_id=other.public_id) == (None, None)


@pytest.mark.django_db
def test_unpaid_immediate_order_production_routes_do_not_render_or_mutate():
    _actor, client = create_staff_client(
        email="unpaid-routes@example.com",
        permissions=[
            "view_order",
            "view_productionjob",
            "assign_productionmachine",
            "confirm_productionprint",
            "scan_productionjob",
            "transition_productionjob",
        ],
    )
    customer = Customer.objects.create(name="Unpaid route customer")
    order = create_order(customer=customer, actor=_actor)
    order.billing_mode = Order.BillingMode.IMMEDIATE
    order.save(update_fields=["billing_mode", "updated_at"])
    kwargs = {"order_public_id": order.public_id}

    assert (
        client.get(reverse("portal:staff-order-panel-production", kwargs=kwargs)).status_code == 404
    )
    assert (
        client.post(
            reverse("portal:staff-order-panel-production", kwargs=kwargs),
            {
                "to_status": ProductionJob.Status.IN_PROGRESS,
            },
        ).status_code
        == 404
    )
    assert client.get(reverse("portal:staff-order-panel-scan", kwargs=kwargs)).status_code == 404
    assert (
        client.post(
            reverse("portal:staff-order-machine-assignment", kwargs=kwargs),
            {
                "machine_public_id": str(order.public_id),
            },
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("portal:staff-order-print-confirmation", kwargs=kwargs),
            {
                "request_token": str(order.public_id),
            },
        ).status_code
        == 404
    )
    assert (
        client.get(reverse("production:staff-manufacturing-order-pdf", kwargs=kwargs)).status_code
        == 404
    )
    order.production_job.refresh_from_db()
    assert order.production_job.status == ProductionJob.Status.QUEUED
    assert order.production_job.of_document_issued_at is None


@pytest.mark.django_db
def test_atelier_dashboard_separates_unprinted_worklist_from_post_issue_kpis():
    actor = get_user_model().objects.create_user(email="tabs@example.com", password="pass")
    customer = Customer.objects.create(name="Tabs Client")
    pending_order = create_order(customer=customer, actor=actor)
    approved_order = create_order(customer=customer, actor=actor)
    add_upload(order=pending_order, actor=actor, filename="pending.pdf", approved=False)
    add_upload(order=approved_order, actor=actor, filename="approved.pdf", approved=True)

    dashboard = AtelierDashboardService().build_dashboard()

    assert len(dashboard["rows"]) == 2
    assert {row["order"].public_id for row in dashboard["rows"]} == {
        pending_order.public_id,
        approved_order.public_id,
    }
    assert dashboard["metrics"] == {
        "unprinted": 2,
        "pending_review": 0,
        "changes_requested": 0,
        "files_validated": 0,
    }


@pytest.mark.django_db
def test_fresh_inbox_count_matches_unprinted_queue_excluding_noise(settings):
    settings.DASHBOARD_EXCLUDED_CUSTOMER_NAMES = ("Compte Test Client",)
    actor = get_user_model().objects.create_user(email="inbox@example.com", password="pass")
    customer = Customer.objects.create(name="Inbox Client")
    noise = Customer.objects.create(name="Compte Test Client")
    live = create_order(customer=customer, actor=actor)
    create_order(customer=noise, actor=actor)
    issued = create_order(customer=customer, actor=actor)
    issued.production_job.of_document_issued_at = timezone.now()
    issued.production_job.save(update_fields=["of_document_issued_at", "updated_at"])
    add_upload(order=live, actor=actor, filename="live.pdf", approved=False)

    assert AtelierDashboardService().fresh_inbox_count() == 1


@pytest.mark.django_db
def test_staff_dashboard_inbox_badge_endpoint_requires_permissions_and_returns_count():
    actor = get_user_model().objects.create_user(
        email="badge@example.com",
        password="pass",
        is_staff=True,
    )
    actor.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    customer = Customer.objects.create(name="Badge Client")
    create_order(customer=customer, actor=actor)
    client = Client()
    assert client.login(email=actor.email, password="pass") is True

    denied = client.get(reverse("portal:staff-dashboard-inbox-badge"))
    assert denied.status_code == 403

    actor.user_permissions.add(
        Permission.objects.get(codename="view_order"),
        Permission.objects.get(codename="view_productionjob"),
    )
    actor = get_user_model().objects.get(pk=actor.pk)
    client.force_login(actor)

    response = client.get(reverse("portal:staff-dashboard-inbox-badge"))
    assert response.status_code == 200
    html = response.content.decode()
    assert 'id="atelier-dashboard-inbox-badge"' in html
    assert "is-active" in html
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'data-inbox-count="1"' in html
    assert ">1<" in html
    assert "hx-get" not in html
    assert "hx-trigger" not in html
    assert "every 20s" not in html


@pytest.mark.django_db
def test_atelier_dashboard_kpis_follow_exclusive_workflow_stages():
    actor = get_user_model().objects.create_user(email="workflow-kpis@example.com", password="pass")
    customer = Customer.objects.create(name="Workflow KPI Client")
    unprinted_order = create_order(customer=customer, actor=actor)
    pending_order = create_order(customer=customer, actor=actor)
    changes_order = create_order(customer=customer, actor=actor)
    approved_order = create_order(customer=customer, actor=actor)
    add_upload(order=unprinted_order, actor=actor, filename="unprinted.pdf", approved=False)
    add_upload(order=pending_order, actor=actor, filename="pending.pdf", approved=False)
    changes_upload = add_upload(
        order=changes_order,
        actor=actor,
        filename="changes.pdf",
        approved=False,
    )
    OrderUploadReview.objects.create(
        order_upload=changes_upload,
        status=OrderUploadReview.Status.CHANGES_REQUESTED,
        reviewed_by=actor,
    )
    add_upload(order=approved_order, actor=actor, filename="approved.pdf", approved=True)
    mark_of_issued(pending_order)
    mark_of_issued(changes_order)
    mark_of_issued(approved_order)

    dashboard = AtelierDashboardService().build_dashboard()

    assert dashboard["metrics"] == {
        "unprinted": 1,
        "pending_review": 1,
        "changes_requested": 1,
        "files_validated": 1,
    }
    assert [row["order"].public_id for row in dashboard["rows"]] == [unprinted_order.public_id]


@pytest.mark.django_db
def test_atelier_dashboard_files_to_process_summary():
    actor = get_user_model().objects.create_user(email="changes@example.com", password="pass")
    customer = Customer.objects.create(name="Changes Client")
    changes_order = create_order(customer=customer, actor=actor)
    approved_order = create_order(customer=customer, actor=actor)
    upload = add_upload(order=changes_order, actor=actor, filename="changes.pdf", approved=False)
    OrderUploadReview.objects.filter(order_upload=upload).delete()
    OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.CHANGES_REQUESTED,
        reviewed_by=actor,
    )
    add_upload(order=approved_order, actor=actor, filename="approved.pdf", approved=True)

    changes_dashboard = AtelierDashboardService().build_dashboard()
    row = next(item for item in changes_dashboard["rows"] if item["order"] == changes_order)

    assert row["files_to_process_count"] == 1
    assert row["files_to_process_label"] == "1 fichier à traiter"
    assert changes_dashboard["metrics"]["changes_requested"] == 0


@pytest.mark.django_db
def test_atelier_dashboard_files_summary_keeps_total_when_it_differs():
    actor = get_user_model().objects.create_user(email="mixed-files@example.com", password="pass")
    customer = Customer.objects.create(name="Fichiers mixtes")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="validated.pdf", approved=True)
    add_upload(order=order, actor=actor, filename="pending.pdf", approved=False)

    dashboard = AtelierDashboardService().build_dashboard()
    row = next(item for item in dashboard["rows"] if item["order"] == order)

    assert row["files_to_process_count"] == 1
    assert row["files_to_process_label"] == "1 à traiter sur 2 fichiers"


@pytest.mark.django_db
def test_order_focus_prioritizes_review_and_only_flags_drive_incidents():
    actor = get_user_model().objects.create_user(email="focus@example.com", password="pass")
    customer = Customer.objects.create(name="Focus Client")
    order = create_order(customer=customer, actor=actor)
    upload = add_upload(order=order, actor=actor, filename="focus.pdf", approved=False)
    service = AtelierDashboardService()

    focus_with_missing_sync = service.build_order_focus(order=order)

    assert focus_with_missing_sync["next_panel"] == "inspection"
    assert focus_with_missing_sync["action_label"] == "Contrôler les visuels"
    assert focus_with_missing_sync["has_drive_issues"] is True

    OrderUploadDriveSync.objects.create(
        order_upload=upload,
        status=OrderUploadDriveSync.Status.SYNCED,
        drive_file_id="drive-file-id",
    )

    focus_with_synced_drive = service.build_order_focus(order=order)

    assert focus_with_synced_drive["has_drive_issues"] is False


@pytest.mark.django_db
def test_batch_service_merges_one_of_per_order_and_marks_issued():
    actor = get_user_model().objects.create_user(email="operator@example.com", password="pass")
    customer = Customer.objects.create(name="Print Client")
    first = create_order(customer=customer, actor=actor)
    second = create_order(customer=customer, actor=actor)
    add_upload(order=first, actor=actor, filename="first.pdf", approved=False)
    add_upload(order=second, actor=actor, filename="second.pdf", approved=True)

    pdf_bytes, orders = ManufacturingOrderBatchService().build_batch_pdf(
        actor=actor,
        order_public_ids=[str(first.public_id), str(second.public_id)],
        mode="selected",
        source="test",
    )

    assert pdf_bytes[:4] == b"%PDF"
    assert len(orders) == 2
    first.production_job.refresh_from_db()
    second.production_job.refresh_from_db()
    assert first.production_job.of_document_issued_at is not None
    assert second.production_job.of_document_issued_at is not None
    assert not OrderUploadReview.objects.filter(order_upload__order=first).exists()
    assert OrderUploadReview.objects.get(order_upload__order=second).status == (
        OrderUploadReview.Status.APPROVED
    )
    metrics = AtelierDashboardService().build_dashboard()["metrics"]
    assert metrics["pending_review"] == 1
    assert metrics["files_validated"] == 1
    audit = AuditLogEntry.objects.get(action="production.manufacturing_orders_batch_downloaded")
    assert audit.actor == actor
    assert AuditLogEntry.objects.filter(
        action="production.manufacturing_orders_marked_issued"
    ).exists()


@pytest.mark.django_db
def test_batch_service_allows_pending_review_orders():
    actor = get_user_model().objects.create_user(email="operator@example.com", password="pass")
    customer = Customer.objects.create(name="Pending Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="pending.pdf", approved=False)

    orders = ManufacturingOrderBatchService().resolve_orders(
        order_public_ids=[str(order.public_id)],
        mode="selected",
    )

    assert orders == [order]


@pytest.mark.django_db
def test_all_unprinted_mode_returns_up_to_max_batch_size_newest_first():
    actor = get_user_model().objects.create_user(email="latest@example.com", password="pass")
    customer = Customer.objects.create(name="Latest Client")
    created_orders = []
    service = ManufacturingOrderBatchService()
    for index in range(service.max_batch_size + 2):
        order = create_order(customer=customer, actor=actor)
        add_upload(
            order=order,
            actor=actor,
            filename=f"ready-{index}.pdf",
            approved=index % 2 == 0,
        )
        created_orders.append(order)

    orders = ManufacturingOrderBatchService().resolve_orders(
        order_public_ids=[],
        mode="all_unprinted",
    )

    assert len(orders) == service.max_batch_size
    assert [order.public_id for order in orders] == [
        order.public_id for order in reversed(created_orders[-service.max_batch_size :])
    ]


@pytest.mark.django_db
def test_atelier_dashboard_lists_full_unissued_queue():
    actor = get_user_model().objects.create_user(email="global@example.com", password="pass")
    customer = Customer.objects.create(name="Global Client")
    service = AtelierDashboardService()
    expected_count = ManufacturingOrderBatchService.max_batch_size + 3
    for index in range(expected_count):
        order = create_order(customer=customer, actor=actor)
        add_upload(
            order=order,
            actor=actor,
            filename=f"open-{index}.pdf",
            approved=False,
        )

    dashboard = service.build_dashboard()
    assert dashboard["metrics"]["unprinted"] == expected_count
    assert dashboard["unprinted_of_total"] == expected_count
    assert len(dashboard["rows"]) == expected_count
    assert dashboard["unprinted_of_batch_count"] == ManufacturingOrderBatchService.max_batch_size


@pytest.mark.django_db
def test_atelier_financial_trend_uses_priced_submitted_orders_over_seven_days():
    actor = get_user_model().objects.create_user(email="revenue-owner@example.com", password="pass")
    customer = Customer.objects.create(name="CA Atelier")
    today_order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        pricing_status=Order.PricingStatus.PRICED,
        billing_mode=Order.BillingMode.DEFERRED,
        total_amount="120.00",
    )
    earlier_order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        pricing_status=Order.PricingStatus.PRICED,
        billing_mode=Order.BillingMode.DEFERRED,
        total_amount="80.00",
    )
    excluded_order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.DRAFT,
        pricing_status=Order.PricingStatus.PRICED,
        billing_mode=Order.BillingMode.DEFERRED,
        total_amount="999.00",
    )
    earlier_day = timezone.now() - timedelta(days=2)
    Order.objects.filter(pk=earlier_order.pk).update(created_at=earlier_day)
    Order.objects.filter(pk=excluded_order.pk).update(created_at=earlier_day)

    trend = AtelierDashboardService().build_financial_trend()

    assert trend["seven_day_total"] == Decimal("200.00")
    assert trend["today_total"] == Decimal("120.00")
    assert trend["average_order_total"] == Decimal("100.00")
    assert trend["order_count"] == 2
    assert trend["revenue_values"][-1] == 120.0
    assert trend["revenue_values"][-3] == 80.0
    assert today_order.pk != excluded_order.pk


@pytest.mark.django_db
def test_atelier_financial_trend_excludes_unpaid_immediate_across_customers():
    actor = get_user_model().objects.create_user(email="cash-trend@example.com", password="pass")
    first_customer = Customer.objects.create(name="Cash trend first")
    second_customer = Customer.objects.create(name="Cash trend second")
    unpaid = Order.objects.create(
        customer=first_customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PRICED,
        total_amount="500.00",
    )
    paid = Order.objects.create(
        customer=second_customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PRICED,
        total_amount="75.00",
    )
    Payment.objects.create(
        order=paid,
        amount="75.00",
        currency="EUR",
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.CAPTURED,
    )

    trend = AtelierDashboardService().build_financial_trend()

    assert trend["seven_day_total"] == Decimal("75.00")
    assert trend["order_count"] == 1
    assert unpaid.pk != paid.pk


@pytest.mark.django_db
def test_atelier_dashboard_excludes_configured_test_customer_from_stats():
    from apps.customers.models import CustomerMembership

    actor = get_user_model().objects.create_user(email="dash-noise@example.com", password="pass")
    real_customer = Customer.objects.create(name="Client réel dashboard")
    test_customer = Customer.objects.create(name="Compte Test Client")
    test_user = get_user_model().objects.create_user(
        email="client.test@prenium.local", password="pass"
    )
    CustomerMembership.objects.create(customer=test_customer, user=test_user)
    real_order = create_order(customer=real_customer, actor=actor)
    test_order = create_order(customer=test_customer, actor=actor)
    real_order.pricing_status = Order.PricingStatus.PRICED
    real_order.total_amount = Decimal("40.00")
    real_order.save(update_fields=["pricing_status", "total_amount", "updated_at"])
    test_order.pricing_status = Order.PricingStatus.PRICED
    test_order.total_amount = Decimal("999.00")
    test_order.save(update_fields=["pricing_status", "total_amount", "updated_at"])

    dashboard = AtelierDashboardService().build_dashboard()
    trend = AtelierDashboardService().build_financial_trend()

    assert [row["order"].public_id for row in dashboard["rows"]] == [real_order.public_id]
    assert trend["seven_day_total"] == Decimal("40.00")
    assert trend["order_count"] == 1


@pytest.mark.django_db
def test_atelier_printed_meterage_trend_uses_print_record_snapshots_and_reprints():
    actor = get_user_model().objects.create_user(
        email="meterage-owner@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Métrage Atelier")
    order = create_order(customer=customer, actor=actor)
    machine = ProductionMachine.objects.create(code="MTR-01", name="Mètre")
    assignment = ProductionJobMachineAssignment.objects.create(
        production_job=order.production_job,
        machine=machine,
        machine_public_id_snapshot=machine.public_id,
        machine_code_snapshot=machine.code,
        machine_name_snapshot=machine.name,
    )
    earlier_record = ProductionPrintRecord.objects.create(
        production_job=order.production_job,
        machine=machine,
        assignment=assignment,
        printed_linear_m="1.2500",
        machine_public_id_snapshot=machine.public_id,
        machine_code_snapshot=machine.code,
        machine_name_snapshot=machine.name,
        manufacturing_order_number_snapshot=order.production_job.manufacturing_order_number,
        order_public_id_snapshot=order.public_id,
        customer_public_id_snapshot=customer.public_id,
    )
    ProductionPrintRecord.objects.create(
        production_job=order.production_job,
        machine=machine,
        assignment=assignment,
        printed_linear_m="0.7500",
        note="Réimpression de contrôle",
        machine_public_id_snapshot=machine.public_id,
        machine_code_snapshot=machine.code,
        machine_name_snapshot=machine.name,
        manufacturing_order_number_snapshot=order.production_job.manufacturing_order_number,
        order_public_id_snapshot=order.public_id,
        customer_public_id_snapshot=customer.public_id,
    )
    ProductionPrintRecord.objects.filter(pk=earlier_record.pk).update(
        printed_at=timezone.now() - timedelta(days=2)
    )

    trend = AtelierDashboardService()._build_printed_meterage_trend()

    assert trend["seven_day_total"] == Decimal("2.0000")
    assert trend["today_total"] == Decimal("0.7500")
    assert trend["average_per_print"] == Decimal("1.0000")
    assert trend["print_count"] == 2
    assert trend["metric_gauges"] == [
        {
            "label": "7 jours",
            "value": Decimal("2.0000"),
            "detail": "2/7 jours actifs",
            "progress": 29,
        },
        {
            "label": "Aujourd’hui",
            "value": Decimal("0.7500"),
            "detail": "vs pic quotidien",
            "progress": 60,
        },
        {
            "label": "Par impression",
            "value": Decimal("1.0000"),
            "detail": "vs plus grand tirage",
            "progress": 80,
        },
    ]


@pytest.mark.django_db
def test_atelier_activity_kpi_excludes_queued_jobs_on_cancelled_orders():
    actor = get_user_model().objects.create_user(
        email="cancelled-queued@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="OF annulée")
    live_order = create_order(customer=customer, actor=actor)
    cancelled_order = create_order(customer=customer, actor=actor)
    Order.objects.filter(pk=cancelled_order.pk).update(status=Order.Status.CANCELLED)

    rows = {
        row["label"]: row["value"] for row in AtelierDashboardService()._build_activity_kpi_rows()
    }
    aging = {
        alert["key"]: alert["value"]
        for alert in AtelierDashboardService()._build_production_health()["alerts"]
    }

    assert live_order.production_job.status == ProductionJob.Status.QUEUED
    assert cancelled_order.production_job.status == ProductionJob.Status.QUEUED
    assert rows["En traitement"] == 1
    assert aging["aging"] == 0


@pytest.mark.django_db
def test_backfill_printed_linear_m_fills_null_snapshots_from_order_meterage():
    import importlib.util
    from pathlib import Path

    from django.apps import apps

    migration_path = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "apps"
        / "production"
        / "migrations"
        / "0008_backfill_printed_linear_m.py"
    )
    spec = importlib.util.spec_from_file_location("backfill_printed_linear_m", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    actor = get_user_model().objects.create_user(
        email="backfill-meterage@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Backfill métrage")
    order = create_order(customer=customer, actor=actor)
    Order.objects.filter(pk=order.pk).update(meterage_override_linear_m=Decimal("3.5000"))
    machine = ProductionMachine.objects.create(code="BF-01", name="Backfill")
    assignment = ProductionJobMachineAssignment.objects.create(
        production_job=order.production_job,
        machine=machine,
        machine_public_id_snapshot=machine.public_id,
        machine_code_snapshot=machine.code,
        machine_name_snapshot=machine.name,
    )
    record = ProductionPrintRecord.objects.create(
        production_job=order.production_job,
        machine=machine,
        assignment=assignment,
        printed_linear_m=None,
        machine_public_id_snapshot=machine.public_id,
        machine_code_snapshot=machine.code,
        machine_name_snapshot=machine.name,
        manufacturing_order_number_snapshot=order.production_job.manufacturing_order_number,
        order_public_id_snapshot=order.public_id,
        customer_public_id_snapshot=customer.public_id,
    )

    module.backfill_printed_linear_m(apps, schema_editor=None)
    record.refresh_from_db()

    assert record.printed_linear_m == Decimal("3.5000")
    trend = AtelierDashboardService()._build_printed_meterage_trend()
    assert trend["seven_day_total"] == Decimal("3.5000")


@pytest.mark.django_db
def test_atelier_production_health_reports_actionable_alerts_quality_and_flow():
    actor = get_user_model().objects.create_user(
        email="production-health@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Pilotage production")
    now = timezone.now()

    blocked_order = create_order(customer=customer, actor=actor)
    ProductionJob.objects.filter(pk=blocked_order.production_job.pk).update(
        status=ProductionJob.Status.BLOCKED,
    )

    overdue_order = create_order(customer=customer, actor=actor)
    Order.objects.filter(pk=overdue_order.pk).update(
        estimated_handover_date=timezone.localdate() - timedelta(days=1),
    )
    ProductionJob.objects.filter(pk=overdue_order.production_job.pk).update(
        status=ProductionJob.Status.IN_PROGRESS,
        last_transition_at=now,
    )

    aging_order = create_order(customer=customer, actor=actor)
    ProductionJob.objects.filter(pk=aging_order.production_job.pk).update(
        status=ProductionJob.Status.QUEUED,
        last_transition_at=None,
        created_at=now - timedelta(hours=25),
    )

    fresh_order = create_order(customer=customer, actor=actor)
    ProductionJob.objects.filter(pk=fresh_order.production_job.pk).update(
        status=ProductionJob.Status.QUEUED,
        last_transition_at=now - timedelta(hours=23),
    )

    two_hour_order = create_order(customer=customer, actor=actor)
    four_hour_order = create_order(customer=customer, actor=actor)
    missing_timestamp_order = create_order(customer=customer, actor=actor)
    ProductionJob.objects.filter(pk=two_hour_order.production_job.pk).update(
        status=ProductionJob.Status.COMPLETED,
        started_at=now - timedelta(hours=2),
        completed_at=now,
    )
    ProductionJob.objects.filter(pk=four_hour_order.production_job.pk).update(
        status=ProductionJob.Status.COMPLETED,
        started_at=now - timedelta(hours=5),
        completed_at=now - timedelta(hours=1),
    )
    ProductionJob.objects.filter(pk=missing_timestamp_order.production_job.pk).update(
        status=ProductionJob.Status.COMPLETED,
        started_at=None,
        completed_at=now,
    )

    print_order = create_order(customer=customer, actor=actor)
    machine = ProductionMachine.objects.create(code="KPI-01", name="KPI")
    assignment = ProductionJobMachineAssignment.objects.create(
        production_job=print_order.production_job,
        machine=machine,
        machine_public_id_snapshot=machine.public_id,
        machine_code_snapshot=machine.code,
        machine_name_snapshot=machine.name,
    )

    def create_print_record(*, note: str = ""):
        return ProductionPrintRecord.objects.create(
            production_job=print_order.production_job,
            machine=machine,
            assignment=assignment,
            note=note,
            machine_public_id_snapshot=machine.public_id,
            machine_code_snapshot=machine.code,
            machine_name_snapshot=machine.name,
            manufacturing_order_number_snapshot=(
                print_order.production_job.manufacturing_order_number
            ),
            order_public_id_snapshot=print_order.public_id,
            customer_public_id_snapshot=customer.public_id,
        )

    historical_print = create_print_record()
    first_recent_reprint = create_print_record(note="Réimpression couleur")
    second_recent_reprint = create_print_record(note="Réimpression contrôle")
    ProductionPrintRecord.objects.filter(pk=historical_print.pk).update(
        created_at=now - timedelta(days=8),
        printed_at=now - timedelta(days=8),
    )
    ProductionPrintRecord.objects.filter(pk=first_recent_reprint.pk).update(
        created_at=now - timedelta(hours=2),
        printed_at=now - timedelta(hours=2),
    )
    ProductionPrintRecord.objects.filter(pk=second_recent_reprint.pk).update(
        created_at=now - timedelta(hours=1),
        printed_at=now - timedelta(hours=1),
    )

    health = AtelierDashboardService()._build_production_health()

    assert health["alerts"] == [
        {
            "key": "blocked",
            "label": "OF bloquées",
            "value": 1,
            "detail": "À débloquer maintenant",
            "tone": "is-danger",
            "href": f"{reverse('portal:staff-order-list')}?status=blocked",
        },
        {
            "key": "overdue",
            "label": "Retards de remise",
            "value": 1,
            "detail": "Date de remise dépassée",
            "tone": "is-danger",
        },
        {
            "key": "aging",
            "label": "Encours > 24 h",
            "value": 1,
            "detail": "Sans progression depuis 24 h",
            "tone": "is-warning",
        },
    ]
    assert health["quality"] == [
        {
            "key": "reprint_rate",
            "label": "Taux de réimpression",
            "value": Decimal("100.0"),
            "unit": "%",
            "detail": "2 sur 2 impressions · 7 j",
            "tone": "is-warning",
        }
    ]
    assert health["flow"] == [
        {
            "key": "average_production_time",
            "label": "Délai moyen de production",
            "value": Decimal("3.0"),
            "unit": "h",
            "detail": "2 OF terminés · 7 j",
            "tone": "is-neutral",
        }
    ]


@pytest.mark.django_db
def test_atelier_production_health_is_safe_without_activity():
    health = AtelierDashboardService()._build_production_health()

    assert [alert["value"] for alert in health["alerts"]] == [0, 0, 0]
    assert [alert["tone"] for alert in health["alerts"]] == [
        "is-success",
        "is-success",
        "is-success",
    ]
    assert health["quality"][0]["value"] == Decimal("0.0")
    assert health["quality"][0]["detail"] == "0 sur 0 impressions · 7 j"
    assert health["flow"][0]["value"] == Decimal("0.0")
    assert health["flow"][0]["detail"] == "0 OF terminés · 7 j"


@pytest.mark.django_db
def test_atelier_financial_dashboard_is_only_rendered_for_owner_or_admin_roles():
    actor = get_user_model().objects.create_user(email="revenue-order@example.com", password="pass")
    customer = Customer.objects.create(name="Revenus Atelier")
    Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        pricing_status=Order.PricingStatus.PRICED,
        billing_mode=Order.BillingMode.DEFERRED,
        total_amount="150.00",
    )
    admin, admin_client = create_staff_client(
        email="admin-revenue@example.com",
        permissions=["view_order", "view_productionjob"],
    )
    collaborator, collaborator_client = create_staff_client(
        email="collaborator-revenue@example.com",
        permissions=["view_order", "view_productionjob"],
    )
    StaffMembership.objects.create(user=admin, role=StaffMembership.Role.ADMIN)
    StaffMembership.objects.create(user=collaborator, role=StaffMembership.Role.MEMBER)

    admin_response = admin_client.get(reverse("portal:staff-dashboard"))
    collaborator_response = collaborator_client.get(reverse("portal:staff-dashboard"))
    collaborator_partial = collaborator_client.get(
        reverse("portal:staff-dashboard"), HTTP_HX_REQUEST="true"
    )

    assert admin_response.context["can_view_financial_trend"] is True
    assert admin_response.context["financial_trend"]["seven_day_total"] == Decimal("150.00")
    assert "Chiffre d’affaires" in admin_response.content.decode()
    assert 'id="atelier-revenue-chart-data"' in admin_response.content.decode()
    assert collaborator_response.context["can_view_financial_trend"] is False
    assert collaborator_response.context["financial_trend"] is None
    assert "Chiffre d’affaires" not in collaborator_response.content.decode()
    assert "atelier-revenue-chart-data" not in collaborator_partial.content.decode()


@pytest.mark.django_db
def test_batch_pdf_route_requires_order_and_production_permissions():
    actor = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Route Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="route.pdf", approved=False)
    route = reverse("portal:staff-manufacturing-order-batch-pdf")

    _limited_user, limited_client = create_staff_client(
        email="limited-batch@example.com",
        permissions=["view_order"],
    )
    denied = limited_client.post(
        route,
        {"batch_mode": "selected", "order_public_ids": [str(order.public_id)]},
    )
    assert denied.status_code == 403

    _staff_user, client = create_staff_client(
        email="allowed-batch@example.com", permissions=["view_order", "view_productionjob"]
    )
    response = client.post(
        route,
        {"batch_mode": "selected", "order_public_ids": [str(order.public_id)]},
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Cache-Control"] == "private, no-store"
    assert response.content[:4] == b"%PDF"
    assert response["Content-Disposition"].startswith("inline;")
    order.production_job.refresh_from_db()
    assert order.production_job.of_document_issued_at is not None


@pytest.mark.django_db
def test_batch_pdf_async_validation_returns_422_with_toast():
    _staff_user, client = create_staff_client(
        email="async-error@example.com",
        permissions=["view_order", "view_productionjob"],
    )
    route = reverse("portal:staff-manufacturing-order-batch-pdf")

    response = client.post(
        route,
        {"batch_mode": "selected", "order_public_ids": [str(uuid.uuid4())]},
        HTTP_X_ATELIER_BATCH="1",
    )

    assert response.status_code == 422
    assert "X-Prenium-Toast" in response
    payload = json.loads(response["X-Prenium-Toast"])
    assert payload["variant"] == "error"


@pytest.mark.django_db
def test_batch_pdf_async_success_returns_pdf_with_toast():
    actor = get_user_model().objects.create_user(email="async-owner@example.com", password="pass")
    customer = Customer.objects.create(name="Async Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="async.pdf", approved=False)
    route = reverse("portal:staff-manufacturing-order-batch-pdf")

    _staff_user, client = create_staff_client(
        email="async-success@example.com",
        permissions=["view_order", "view_productionjob"],
    )
    response = client.post(
        route,
        {"batch_mode": "selected", "order_public_ids": [str(order.public_id)]},
        HTTP_X_ATELIER_BATCH="1",
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    assert response["Content-Disposition"].startswith("inline;")
    assert "X-Prenium-Batch-Order-Ids" in response
    printed_ids = json.loads(response["X-Prenium-Batch-Order-Ids"])
    assert printed_ids == [str(order.public_id)]
    payload = json.loads(response["X-Prenium-Toast"])
    assert payload["variant"] == "success"
    assert "1 OF" in payload["message"]
    assert "aperçu" in payload["message"].lower()
    order.production_job.refresh_from_db()
    assert order.production_job.of_document_issued_at is not None


@pytest.mark.django_db
def test_staff_dashboard_hx_returns_worklist_panel_partial():
    actor = get_user_model().objects.create_user(email="hx-owner@example.com", password="pass")
    customer = Customer.objects.create(name="HX Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="hx.pdf", approved=False)

    _staff_user, client = create_staff_client(
        email="hx-dashboard@example.com",
        permissions=["view_order", "view_productionjob"],
    )
    response = client.get(reverse("portal:staff-dashboard"), HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    content = response.content.decode()
    assert 'id="atelier-dashboard-panel"' in content
    assert "data-atelier-batch" in content
    assert str(order.public_id) in content
    assert ">UUID<" not in content
    assert "data-clipboard-copy" in content


@pytest.mark.django_db
def test_external_order_without_meterage_is_print_eligible_on_dashboard():
    """OF émissible avant métrage / contrôle — gate production ≠ gate impression OF."""
    from apps.orders.services.external_orders import ExternalOrderService

    actor = get_user_model().objects.create_user(
        email="external-of@example.com", password="pass", is_staff=True
    )
    actor.user_permissions.add(
        *[
            Permission.objects.get(codename=name)
            for name in (
                "access_staff_portal",
                "add_order",
                "change_order",
                "view_order",
            )
        ]
    )
    customer = Customer.objects.create(name="Lien OF Client")
    order = ExternalOrderService().create_staff_order(
        customer=customer,
        actor=actor,
        name="Lien sans métrage",
        external_url="https://files.example.com/lot",
        meterage_linear_m=None,
        shipping_method_code="standard",
    )
    assert order.meterage_override_linear_m is None
    assert order.pricing_status == Order.PricingStatus.PENDING

    dashboard = AtelierDashboardService().build_dashboard()
    row = next(r for r in dashboard["rows"] if r["order"].public_id == order.public_id)
    assert row["print_eligible"] is True

    pdf = render_manufacturing_order_pdf_bytes(order=order, production_job=order.production_job)
    assert pdf.startswith(b"%PDF")
