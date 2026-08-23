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
    assert "Expédition" in html
    assert "Votre référence" not in html
    assert "Accueil client" not in html
    assert "client-order-panel-billing" not in html
    assert 'panel=billing"' not in html and "?panel=billing" not in html

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
    assert shipping.status_code == 200
    assert "Expédition" in shipping.content.decode()
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
    assert "Les étapes confirmées par l’atelier" not in html
    assert "Commande transmise" in html
    assert "En production" in html
    assert "Lancement atelier" in html
    assert 'hx-swap-oob="outerHTML:#client-order-breadcrumb"' in html
    assert "Avancement" in html


@pytest.mark.django_db
def test_owner_shipping_panel_owns_the_primary_tracking_action():
    from apps.shipping.models import Shipment
    from django.utils import timezone

    user = get_user_model().objects.create_user(email="ship-owner@example.com", password="pass")
    customer = Customer.objects.create(name="Ship Owner")
    CustomerMembership.objects.create(
        customer=customer, user=user, role=CustomerMembership.Role.OWNER
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    Shipment.objects.create(
        order=order,
        status=Shipment.Status.CREATED,
        shipping_option_code="sendcloud:letter",
        tracking_number="TRK-CLIENT-001",
        tracking_url="https://tracking.example.test/TRK-CLIENT-001",
        sendcloud_status_code="IN_TRANSIT",
        sendcloud_status_message="En transit",
        shipped_at=timezone.now(),
        source="test",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")

    detail = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    detail_html = detail.content.decode()
    assert detail.status_code == 200
    assert "TRK-CLIENT-001" not in detail_html
    assert "Suivre le colis" not in detail_html

    shipping = client.get(
        reverse(
            "portal:client-order-panel-shipping",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    shipping_html = shipping.content.decode()
    assert shipping.status_code == 200
    assert "Votre commande est en route" in shipping_html
    assert "TRK-CLIENT-001" in shipping_html
    assert "Suivre mon colis" in shipping_html
    assert "client-shipment-card--shipped" in shipping_html

    production = client.get(
        reverse(
            "portal:client-order-panel-production",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    production_html = production.content.decode()
    assert production.status_code == 200
    assert "Commande expédiée" in production_html
    assert "TRK-CLIENT-001" in production_html
    assert "Suivre mon colis" in production_html


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
        status=Order.Status.DRAFT,
        source="client_portal",
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PENDING,
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
    order.status = Order.Status.SUBMITTED
    order.save(update_fields=["status", "updated_at"])

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
    assert "Visuels transmis" not in panel.content.decode()
