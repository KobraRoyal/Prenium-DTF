from __future__ import annotations

import pytest
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.services.dashboard import AtelierDashboardService
from apps.production.services.staff_order_list_filters import StaffOrderListFilterService
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUpload, OrderUploadReview
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


def create_staff_client(*, email: str):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    user.user_permissions.add(Permission.objects.get(codename="view_order"))
    client = Client()
    assert client.login(email=user.email, password="pass")
    return client


@pytest.mark.django_db
def test_staff_order_list_filter_service_matches_dashboard_segments():
    actor = get_user_model().objects.create_user(email="filters@example.com", password="pass")
    customer = Customer.objects.create(name="Filter Client")
    pending_order = create_order(customer=customer, actor=actor)
    approved_order = create_order(customer=customer, actor=actor)
    changes_order = create_order(customer=customer, actor=actor)
    issued_order = create_order(customer=customer, actor=actor)
    add_upload(order=pending_order, actor=actor, filename="pending.pdf", approved=False)
    add_upload(order=approved_order, actor=actor, filename="approved.pdf", approved=True)
    upload = add_upload(order=changes_order, actor=actor, filename="changes.pdf", approved=False)
    OrderUploadReview.objects.filter(order_upload=upload).delete()
    OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.CHANGES_REQUESTED,
        reviewed_by=actor,
    )
    add_upload(order=issued_order, actor=actor, filename="issued.pdf", approved=True)
    issued_order.production_job.of_document_issued_at = timezone.now()
    issued_order.production_job.save(update_fields=["of_document_issued_at", "updated_at"])

    from apps.orders.services.orders import OrderService

    base = OrderService().list_staff_orders()
    service = StaffOrderListFilterService()
    counts = service.count_by_queue(base)

    assert counts["unprinted"] == 3
    assert counts["to_review"] == 1
    assert counts["changes"] == 1
    assert counts["approved"] == 1

    unprinted_ids = set(
        service.apply_filter(base, queue="unprinted").values_list("public_id", flat=True)
    )
    assert unprinted_ids == {
        pending_order.public_id,
        approved_order.public_id,
        changes_order.public_id,
    }


@pytest.mark.django_db
def test_dashboard_kpi_cards_link_to_staff_orders_filters():
    actor = get_user_model().objects.create_user(email="kpi@example.com", password="pass")
    customer = Customer.objects.create(name="KPI Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="open.pdf", approved=False)

    dashboard = AtelierDashboardService().build_dashboard()
    hrefs = {row["label"]: row["card_href"] for row in dashboard["kpi_rows"]}
    orders_url = reverse("portal:staff-order-list")

    assert hrefs["OF non imprimés"] == f"{orders_url}?queue=unprinted"
    assert hrefs["À contrôler"] == f"{orders_url}?queue=to_review"
    assert hrefs["Corrections client"] == f"{orders_url}?queue=changes"
    assert hrefs["Fichiers validés"] == f"{orders_url}?queue=approved"


@pytest.mark.django_db
def test_staff_order_list_renders_queue_filter_tabs():
    actor = get_user_model().objects.create_user(email="list@example.com", password="pass")
    customer = Customer.objects.create(name="List Client")
    order = create_order(customer=customer, actor=actor)
    add_upload(order=order, actor=actor, filename="open.pdf", approved=False)

    client = create_staff_client(email="staff-list@example.com")
    response = client.get(reverse("portal:staff-order-list"), {"queue": "to_review"})

    assert response.status_code == 200
    html = response.content.decode()
    assert 'aria-label="Filtrer les commandes Atelier"' in html
    assert "OF non imprimés" in html
    assert "ui-data-table" in html
