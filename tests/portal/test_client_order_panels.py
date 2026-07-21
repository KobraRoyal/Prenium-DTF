import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob, ProductionJobTransition
from django.contrib.auth import get_user_model
from django.test import Client, override_settings
from django.urls import reverse

from tests.b2b_order_projects.helpers import create_scope, png_upload


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_member_cannot_access_owner_order_panels():
    user, customer, _api = create_scope(
        "member-panels@example.com",
        role=CustomerMembership.Role.MEMBER,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    detail = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    html = detail.content.decode()
    assert detail.status_code == 200
    assert "Visuels" in html
    assert "Avancement" in html
    assert "Expédition" not in html
    assert "Facture" not in html

    shipping = client.get(
        reverse(
            "portal:client-order-panel-shipping",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    billing = client.get(
        reverse(
            "portal:client-order-panel-billing",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    assert shipping.status_code == 403
    assert billing.status_code == 403


@pytest.mark.django_db
def test_production_panel_shows_status_history():
    user = get_user_model().objects.create_user(email="timeline@example.com", password="pass")
    customer = Customer.objects.create(name="Timeline Client")
    CustomerMembership.objects.create(
        customer=customer, user=user, role=CustomerMembership.Role.MEMBER
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    job = ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-TEST-001",
        status=ProductionJob.Status.IN_PROGRESS,
    )
    ProductionJobTransition.objects.create(
        production_job=job,
        from_status=ProductionJob.Status.QUEUED,
        to_status=ProductionJob.Status.IN_PROGRESS,
        changed_by=user,
        reason="Lancement atelier",
        source="staff_api",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(
        reverse(
            "portal:client-order-panel-production",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "Historique des statuts" in html
    assert "client-order-panel--production" in html
    assert "Les étapes confirmées par l’atelier" in html
    assert "Commande transmise" in html
    assert "En production" in html
    assert "Lancement atelier" in html
    assert 'hx-swap-oob="outerHTML:#client-order-breadcrumb"' in html
    assert "Avancement" in html


@pytest.mark.django_db
def test_order_detail_breadcrumb_shows_active_panel():
    user = get_user_model().objects.create_user(email="breadcrumb@example.com", password="pass")
    customer = Customer.objects.create(name="Breadcrumb Client")
    CustomerMembership.objects.create(
        customer=customer, user=user, role=CustomerMembership.Role.MEMBER
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
            },
        )
        + "?panel=production"
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert 'id="client-order-breadcrumb"' in html
    assert "Avancement" in html
    assert ">Détail</span>" not in html


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_reorder_from_order_creates_project_with_visuals():
    user, customer, _api = create_scope(
        "reorder@example.com",
        role=CustomerMembership.Role.MEMBER,
        enabled=True,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    upload_client = Client()
    assert upload_client.login(email=user.email, password="pass")
    upload_client.post(
        reverse(
            "uploads:client-order-upload-list-create",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        ),
        {"file": png_upload(), "quantity": "2", "support_color_hex": "#112233"},
        format="multipart",
    )

    response = upload_client.post(
        reverse(
            "portal:client-order-reorder",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    assert response.status_code == 302
    assert "/order-projects/" in response["Location"]

    panel = upload_client.get(
        reverse(
            "portal:client-order-panel-uploads",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    assert "Réassort" in panel.content.decode()
