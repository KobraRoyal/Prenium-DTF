from __future__ import annotations

import json
import uuid

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.dashboard import AtelierDashboardService
from apps.production.services.manufacturing_order_batch import (
    ManufacturingOrderBatchService,
)
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUpload, OrderUploadDriveSync, OrderUploadReview
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
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
    issued.production_job.of_document_issued_at = timezone.now()
    issued.production_job.save(update_fields=["of_document_issued_at", "updated_at"])
    completed.production_job.status = ProductionJob.Status.COMPLETED
    completed.production_job.save(update_fields=["status", "updated_at"])

    dashboard = AtelierDashboardService().build_dashboard()

    assert [row["order"].public_id for row in dashboard["rows"]] == [unissued.public_id]
    assert dashboard["unprinted_of_total"] == 1


@pytest.mark.django_db
def test_atelier_dashboard_lists_all_unissued_orders_without_filters():
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
        "pending_review": 1,
        "changes_requested": 0,
        "files_validated": 1,
    }


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
    assert row["files_to_process_label"] == "1 à traiter"
    assert changes_dashboard["metrics"]["changes_requested"] == 1


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
