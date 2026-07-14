from __future__ import annotations

import pymupdf
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
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse


def create_order(*, customer, actor, status=Order.Status.SUBMITTED):
    order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=status,
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
def test_atelier_dashboard_focuses_on_submitted_orders_and_review_state():
    actor = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Atelier Client")
    ready_order = create_order(customer=customer, actor=actor)
    pending_order = create_order(customer=customer, actor=actor)
    create_order(customer=customer, actor=actor, status=Order.Status.DRAFT)
    add_upload(order=ready_order, actor=actor, filename="ready.pdf", approved=True)
    add_upload(order=pending_order, actor=actor, filename="pending.pdf", approved=False)

    dashboard = AtelierDashboardService().build_dashboard(active_tab="all")

    rows_by_id = {row["order"].public_id: row for row in dashboard["rows"]}
    assert len(rows_by_id) == 2
    assert rows_by_id[ready_order.public_id]["ready_to_print"] is True
    assert rows_by_id[ready_order.public_id]["print_eligible"] is True
    assert rows_by_id[pending_order.public_id]["review_status"] == "pending"
    assert rows_by_id[pending_order.public_id]["print_eligible"] is False
    assert dashboard["metrics"]["ready_to_print"] == 1
    assert dashboard["metrics"]["pending_review"] == 1


@pytest.mark.django_db
def test_atelier_dashboard_tabs_filter_one_shared_worklist():
    actor = get_user_model().objects.create_user(email="tabs@example.com", password="pass")
    customer = Customer.objects.create(name="Tabs Client")
    ready_order = create_order(customer=customer, actor=actor)
    pending_order = create_order(customer=customer, actor=actor)
    production_order = create_order(customer=customer, actor=actor)
    add_upload(order=ready_order, actor=actor, filename="ready.pdf", approved=True)
    add_upload(order=pending_order, actor=actor, filename="pending.pdf", approved=False)
    add_upload(order=production_order, actor=actor, filename="production.pdf", approved=True)
    production_order.production_job.status = ProductionJob.Status.IN_PROGRESS
    production_order.production_job.save(update_fields=["status", "updated_at"])

    default_dashboard = AtelierDashboardService().build_dashboard(active_tab="unknown")
    ready_dashboard = AtelierDashboardService().build_dashboard(active_tab="ready")
    production_dashboard = AtelierDashboardService().build_dashboard(active_tab="production")

    assert default_dashboard["active_tab"] == "to_review"
    assert [row["order"] for row in default_dashboard["rows"]] == [pending_order]
    assert [row["order"] for row in ready_dashboard["rows"]] == [ready_order]
    assert [row["order"] for row in production_dashboard["rows"]] == [production_order]
    counts = {tab["key"]: tab["count"] for tab in ready_dashboard["tabs"]}
    assert counts == {"to_review": 1, "ready": 1, "production": 1, "all": 3}


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
def test_batch_service_merges_one_of_per_order_and_records_audit():
    actor = get_user_model().objects.create_user(email="operator@example.com", password="pass")
    customer = Customer.objects.create(name="Print Client")
    first = create_order(customer=customer, actor=actor)
    second = create_order(customer=customer, actor=actor)
    add_upload(order=first, actor=actor, filename="first.pdf", approved=True)
    add_upload(order=second, actor=actor, filename="second.pdf", approved=True)

    pdf_bytes, orders = ManufacturingOrderBatchService().build_batch_pdf(
        actor=actor,
        order_public_ids=[str(first.public_id), str(second.public_id)],
        mode="selected",
        source="test",
    )

    assert pdf_bytes[:4] == b"%PDF"
    assert len(orders) == 2
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)
        assert document.page_count == 2
    assert first.production_job.manufacturing_order_number in text
    assert second.production_job.manufacturing_order_number in text
    audit = AuditLogEntry.objects.get(action="production.manufacturing_orders_batch_downloaded")
    assert audit.actor == actor
    assert audit.metadata["order_count"] == 2


@pytest.mark.django_db
def test_batch_service_refuses_order_before_atelier_approval():
    actor = get_user_model().objects.create_user(email="operator@example.com", password="pass")
    customer = Customer.objects.create(name="Pending Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="pending.pdf", approved=False)

    with pytest.raises(ValidationError, match="Validez tous les fichiers Atelier"):
        ManufacturingOrderBatchService().resolve_orders(
            order_public_ids=[str(order.public_id)],
            mode="selected",
        )


@pytest.mark.django_db
def test_latest_ready_mode_returns_only_the_five_newest_approved_orders():
    actor = get_user_model().objects.create_user(email="latest@example.com", password="pass")
    customer = Customer.objects.create(name="Latest Client")
    created_orders = []
    for index in range(6):
        order = create_order(customer=customer, actor=actor)
        add_upload(
            order=order,
            actor=actor,
            filename=f"ready-{index}.pdf",
            approved=True,
        )
        created_orders.append(order)

    orders = ManufacturingOrderBatchService().resolve_orders(
        order_public_ids=[],
        mode="latest_ready",
    )

    assert len(orders) == 5
    assert [order.public_id for order in orders] == [
        order.public_id for order in reversed(created_orders[1:])
    ]


@pytest.mark.django_db
def test_batch_pdf_route_requires_order_and_production_permissions():
    actor = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Route Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="route.pdf", approved=True)
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
