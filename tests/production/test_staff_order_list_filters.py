from __future__ import annotations

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.models import ProductionJob
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


def mark_of_issued(order):
    order.production_job.of_document_issued_at = timezone.now()
    order.production_job.save(update_fields=["of_document_issued_at", "updated_at"])


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
    unprinted_order = create_order(customer=customer, actor=actor)
    add_upload(order=pending_order, actor=actor, filename="pending.pdf", approved=False)
    add_upload(order=approved_order, actor=actor, filename="approved.pdf", approved=True)
    upload = add_upload(order=changes_order, actor=actor, filename="changes.pdf", approved=False)
    OrderUploadReview.objects.filter(order_upload=upload).delete()
    OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.CHANGES_REQUESTED,
        reviewed_by=actor,
    )
    add_upload(order=unprinted_order, actor=actor, filename="unprinted.pdf", approved=False)
    mark_of_issued(pending_order)
    mark_of_issued(approved_order)
    mark_of_issued(changes_order)

    from apps.orders.services.orders import OrderService

    base = OrderService().list_staff_orders()
    service = StaffOrderListFilterService()
    counts = service.count_by_queue(base)

    assert counts["unprinted"] == 1
    assert counts["to_review"] == 1
    assert counts["changes"] == 1
    assert counts["approved"] == 1

    unprinted_ids = set(
        service.apply_filter(base, queue="unprinted").values_list("public_id", flat=True)
    )
    assert unprinted_ids == {unprinted_order.public_id}
    assert set(
        service.apply_filter(base, queue="to_review").values_list("public_id", flat=True)
    ) == {pending_order.public_id}
    assert set(service.apply_filter(base, queue="changes").values_list("public_id", flat=True)) == {
        changes_order.public_id
    }
    assert set(
        service.apply_filter(base, queue="approved").values_list("public_id", flat=True)
    ) == {approved_order.public_id}


@pytest.mark.django_db
def test_staff_order_list_filter_service_filters_by_production_status():
    actor = get_user_model().objects.create_user(
        email="status-filters@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Status filter client")
    create_order(customer=customer, actor=actor)
    in_progress_order = create_order(customer=customer, actor=actor)
    ready_order = create_order(customer=customer, actor=actor)
    in_progress_order.production_job.status = ProductionJob.Status.IN_PROGRESS
    in_progress_order.production_job.save(update_fields=["status", "updated_at"])
    ready_order.production_job.status = ProductionJob.Status.READY_TO_SHIP
    ready_order.production_job.save(update_fields=["status", "updated_at"])

    from apps.orders.services.orders import OrderService

    base = OrderService().list_staff_orders()
    service = StaffOrderListFilterService()

    assert service.count_by_status(base)[ProductionJob.Status.QUEUED] == 1
    assert service.count_by_status(base)[ProductionJob.Status.IN_PROGRESS] == 1
    assert service.count_by_status(base)[ProductionJob.Status.READY_TO_SHIP] == 1
    assert set(
        service.apply_status_filter(base, status=ProductionJob.Status.READY_TO_SHIP).values_list(
            "public_id", flat=True
        )
    ) == {ready_order.public_id}
    assert service.normalize_status("unknown") == ""


@pytest.mark.django_db
def test_staff_order_list_search_matches_of_order_and_customer_references():
    actor = get_user_model().objects.create_user(
        email="search-filters@example.com", password="pass"
    )
    alpha_customer = Customer.objects.create(name="Atelier Alpha")
    beta_customer = Customer.objects.create(name="Atelier Beta")
    gamma_customer = Customer.objects.create(name="Atelier Gamma")
    alpha_order = create_order(customer=alpha_customer, actor=actor)
    beta_order = create_order(customer=beta_customer, actor=actor)
    gamma_order = create_order(
        customer=gamma_customer,
        actor=actor,
        status=Order.Status.DRAFT,
    )
    B2BOrderProject.objects.create(
        customer=alpha_customer,
        created_by=actor,
        project_number="CMD-2026-000321",
        name="Collection Alpha",
        customer_reference="REF-ALPHA",
        converted_order=alpha_order,
        status=B2BOrderProject.Status.CONVERTED,
    )

    from apps.orders.services.orders import OrderService

    base = OrderService().list_staff_orders()
    service = StaffOrderListFilterService()
    alpha_id = [alpha_order.pk]

    for query in (
        alpha_order.production_job.manufacturing_order_number,
        "CMD-2026-000321",
        "REF-ALPHA",
        "Atelier Alpha",
    ):
        assert (
            list(service.apply_search(base, query=query).values_list("pk", flat=True)) == alpha_id
        )

    assert service.apply_search(base, query="   ").count() == 3
    assert list(service.apply_search(base, query="Atelier Gamma").values_list("pk", flat=True)) == [
        gamma_order.pk
    ]
    assert beta_order.pk not in service.apply_search(
        base,
        query=alpha_order.production_job.manufacturing_order_number,
    ).values_list("pk", flat=True)


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
    mark_of_issued(order)

    client = create_staff_client(email="staff-list@example.com")
    response = client.get(reverse("portal:staff-order-list"), {"queue": "to_review"})

    assert response.status_code == 200
    html = response.content.decode()
    assert 'aria-label="Filtrer les commandes Atelier"' in html
    assert "OF non imprimés" in html
    assert "ui-data-table" in html


@pytest.mark.django_db
def test_staff_order_list_search_preserves_queue_and_displays_of_instead_of_uuid():
    actor = get_user_model().objects.create_user(email="list-search@example.com", password="pass")
    customer = Customer.objects.create(name="List Search")
    matching_order = create_order(customer=customer, actor=actor)
    other_order = create_order(customer=customer, actor=actor)
    matching_of = matching_order.production_job.manufacturing_order_number
    other_of = other_order.production_job.manufacturing_order_number

    client = create_staff_client(email="staff-list-search@example.com")
    response = client.get(
        reverse("portal:staff-order-list"),
        {"queue": "unprinted", "q": matching_of},
    )

    assert response.status_code == 200
    assert response.context["search_query"] == matching_of
    assert response.context["active_queue"] == "unprinted"
    assert response.context["active_production_status"] == ""
    html = response.content.decode()
    assert 'id="staff-orders-search-input"' in html
    assert f'value="{matching_of}"' in html
    assert 'hx-trigger="input changed delay:300ms, search"' in html
    assert 'hx-target="#staff-orders-list-results"' in html
    assert 'hx-include="closest form"' in html
    assert 'id="staff-orders-search-input-status"' in html
    assert f"q={matching_of}" in html
    assert matching_of in html
    assert other_of not in html
    assert "N° OF" in html
    assert ">UUID<" not in html

    partial_response = client.get(
        reverse("portal:staff-order-list"),
        {"queue": "unprinted", "q": matching_of},
        HTTP_HX_REQUEST="true",
    )

    assert partial_response.status_code == 200
    partial_html = partial_response.content.decode()
    assert 'class="staff-orders-results ui-list-results"' in partial_html
    assert 'id="staff-orders-search-input"' not in partial_html
    assert "portal-page--staff" not in partial_html
    assert matching_of in partial_html
    assert other_of not in partial_html


@pytest.mark.django_db
def test_staff_order_list_status_filter_preserves_the_queue_and_search():
    actor = get_user_model().objects.create_user(email="list-status@example.com", password="pass")
    customer = Customer.objects.create(name="List status client")
    ready_order = create_order(customer=customer, actor=actor)
    queued_order = create_order(customer=customer, actor=actor)
    ready_order.production_job.status = ProductionJob.Status.READY_TO_SHIP
    ready_order.production_job.save(update_fields=["status", "updated_at"])

    client = create_staff_client(email="staff-list-status@example.com")
    response = client.get(
        reverse("portal:staff-order-list"),
        {"queue": "", "status": ProductionJob.Status.READY_TO_SHIP, "q": "List status"},
    )

    assert response.status_code == 200
    assert response.context["active_production_status"] == ProductionJob.Status.READY_TO_SHIP
    html = response.content.decode()
    assert 'id="staff-orders-search-input-status"' in html
    assert "Prêtes à expédier" in html
    assert ready_order.production_job.manufacturing_order_number in html
    assert queued_order.production_job.manufacturing_order_number not in html
    assert 'name="queue" type="hidden" value=""' in html
    assert '<option value="ready_to_ship" selected>' in html
