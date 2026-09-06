from datetime import date, datetime

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob, ProductionJobTransition
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
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
    assert "Livraison" in html
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
        customer_note="Collection été\nLivraison avant ouverture",
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
    assert "Collection été" in html


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
    assert "Commande en route" in shipping_html
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
    assert "Expédiée" in production_html
    assert "TRK-CLIENT-001" in production_html
    assert "Suivre mon colis" in production_html


@pytest.mark.django_db
def test_client_shipping_panel_shows_delivered_carrier_state():
    from apps.shipping.models import Shipment
    from django.utils import timezone

    user = get_user_model().objects.create_user(
        email="delivered-owner@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Delivered Client")
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
        shipping_method_code="standard",
    )
    Shipment.objects.create(
        order=order,
        status=Shipment.Status.CREATED,
        shipping_option_code="sendcloud:letter",
        tracking_number="TRK-CLIENT-DELIVERED",
        sendcloud_status_code="DELIVERED",
        sendcloud_status_message="Livré",
        shipped_at=timezone.now(),
        source="test",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(
        reverse(
            "portal:client-order-panel-shipping",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert "Commande livrée" in html
    assert "Commande en route" not in html
    assert "client-shipment-card--shipped" in html


@pytest.mark.django_db
def test_pickup_shipping_panel_prioritizes_collection_over_carrier_metadata():
    from apps.shipping.models import Shipment

    user = get_user_model().objects.create_user(email="pickup-ready@example.com", password="pass")
    customer = Customer.objects.create(name="Pickup Ready Client")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.MEMBER,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
        shipping_method_code="pickup",
        estimated_handover_date=date(2026, 9, 15),
    )
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-PICKUP-READY",
        status=ProductionJob.Status.READY_TO_SHIP,
    )
    Shipment.objects.create(
        order=order,
        status=Shipment.Status.CREATED,
        shipping_option_code="sendcloud:letter",
        tracking_number="TRK-PICKUP-HIDE",
        tracking_url="https://tracking.example.test/TRK-PICKUP-HIDE",
        sendcloud_status_message="Declared in Sendcloud — awaiting label",
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
    shipping = client.get(
        reverse(
            "portal:client-order-panel-shipping",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    production = client.get(
        reverse(
            "portal:client-order-panel-production",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )

    detail_html = detail.content.decode()
    shipping_html = shipping.content.decode()
    production_html = production.content.decode()
    assert detail.status_code == 200
    assert shipping.status_code == 200
    assert production.status_code == 200
    assert "Retrait" in detail_html
    assert "Prête au retrait" in shipping_html
    assert "Disponible à l’atelier." in shipping_html
    assert "Statut" not in shipping_html
    assert "Retrait prévu" in shipping_html
    assert "15/09/2026" in shipping_html
    assert "Sendcloud" not in shipping_html
    assert "Declared in Sendcloud" not in shipping_html
    assert "TRK-PICKUP-HIDE" not in shipping_html
    assert "Suivre mon colis" not in shipping_html
    assert "Prête au retrait" in production_html
    assert "Expédition en préparation" not in production_html
    assert "Declared in Sendcloud" not in production_html


@pytest.mark.django_db
def test_pickup_shipping_panel_dates_the_confirmed_collection():
    from apps.shipping.models import Shipment
    from django.utils import timezone

    user = get_user_model().objects.create_user(
        email="pickup-completed@example.com", password="pass"
    )
    customer = Customer.objects.create(name="Pickup Completed Client")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.MEMBER,
    )
    collected_at = timezone.make_aware(datetime(2026, 8, 29, 11, 6))
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
        shipping_method_code="pickup",
    )
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-PICKUP-COMPLETED",
        status=ProductionJob.Status.COMPLETED,
        completed_at=collected_at,
    )
    Shipment.objects.create(
        order=order,
        status=Shipment.Status.CREATED,
        shipping_option_code="sendcloud:letter",
        tracking_number="TRK-PICKUP-COMPLETED",
        tracking_url="https://tracking.example.test/TRK-PICKUP-COMPLETED",
        sendcloud_status_message="Declared in Sendcloud — awaiting label",
        shipped_at=collected_at,
        source="test",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(
        reverse(
            "portal:client-order-panel-shipping",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert "Commande retirée" in html
    assert "Statut" not in html
    assert "Retrait effectué" in html
    assert "29/08/2026 · 11:06" in html
    assert "Sendcloud" not in html
    assert "TRK-PICKUP-COMPLETED" not in html
    assert "Suivre mon colis" not in html


@pytest.mark.django_db
def test_client_timeline_keeps_carrier_payload_private():
    from apps.shipping.models import Shipment
    from django.utils import timezone

    user = get_user_model().objects.create_user(
        email="timeline-carrier@example.com", password="pass"
    )
    customer = Customer.objects.create(name="Timeline Carrier Client")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.MEMBER,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
        shipping_method_code="standard",
    )
    Shipment.objects.create(
        order=order,
        status=Shipment.Status.CREATED,
        shipping_option_code="sendcloud:letter",
        tracking_number="TRK-CLIENT-TIMELINE",
        tracking_url="https://tracking.example.test/TRK-CLIENT-TIMELINE",
        sendcloud_status_code="IN_TRANSIT",
        sendcloud_status_message="Declared in Sendcloud — awaiting label",
        shipped_at=timezone.now(),
        source="test",
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
    assert "Expédiée" in html
    assert "TRK-CLIENT-TIMELINE" in html
    assert "Sendcloud" not in html
    assert "Declared in Sendcloud" not in html


@pytest.mark.django_db
def test_client_order_views_share_operational_status_and_handover_date():
    user = get_user_model().objects.create_user(email="status-list@example.com", password="pass")
    customer = Customer.objects.create(name="Status Client")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.MEMBER,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        shipping_method_code="pickup",
        estimated_handover_date=date(2026, 9, 15),
    )
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-STATUS-001",
        status=ProductionJob.Status.IN_PROGRESS,
    )

    client = Client()
    assert client.login(email=user.email, password="pass")

    list_response = client.get(
        reverse(
            "portal:client-order-list",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    list_html = list_response.content.decode()
    assert list_response.status_code == 200
    assert "En production" in list_html
    assert "Date annoncée" in list_html
    assert "15/09/2026" in list_html

    detail_response = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
            },
        )
    )
    detail_html = detail_response.content.decode()
    assert detail_response.status_code == 200
    assert '<span class="badge is-warning">En production</span>' in detail_html
    assert "Retrait prévu" in detail_html
    assert "15/09/2026" in detail_html
    assert '<span class="badge is-neutral">Soumise</span>' not in detail_html


@pytest.mark.django_db
def test_client_order_list_shows_completed_pickup_instead_of_an_unconfirmed_estimate():
    user = get_user_model().objects.create_user(email="pickup-list@example.com", password="pass")
    customer = Customer.objects.create(name="Pickup list client")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        shipping_method_code="pickup",
    )
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-PICKUP-LIST-COMPLETED",
        status=ProductionJob.Status.COMPLETED,
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer.public_id})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Retrait" in html
    assert "Effectué" in html


@pytest.mark.django_db
def test_staff_can_update_handover_date_with_audited_change():
    staff_user = get_user_model().objects.create_user(
        email="handover-date-staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_order"),
        Permission.objects.get(codename="view_productionjob"),
        Permission.objects.get(codename="change_order"),
    )
    customer = Customer.objects.create(name="Handover Date Client")
    order = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
        shipping_method_code="standard",
    )
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-HANDOVER-001",
        status=ProductionJob.Status.QUEUED,
    )

    client = Client()
    assert client.login(email=staff_user.email, password="pass")
    response = client.post(
        reverse(
            "portal:staff-order-panel-production",
            kwargs={"order_public_id": order.public_id},
        ),
        {"action": "update_handover_date", "estimated_handover_date": "2026-09-18"},
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.estimated_handover_date == date(2026, 9, 18)
    assert AuditLogEntry.objects.filter(
        action="order.estimated_handover_date_updated",
        target_public_id=order.public_id,
        metadata__estimated_handover_date="2026-09-18",
    ).exists()

    client.post(
        reverse(
            "portal:staff-order-panel-production",
            kwargs={"order_public_id": order.public_id},
        ),
        {"action": "update_handover_date", "estimated_handover_date": ""},
    )
    order.refresh_from_db()
    assert order.estimated_handover_date is None


@pytest.mark.django_db
def test_staff_without_order_change_cannot_update_handover_date():
    staff_user = get_user_model().objects.create_user(
        email="handover-date-readonly@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_order"),
        Permission.objects.get(codename="view_productionjob"),
    )
    customer = Customer.objects.create(name="Readonly Handover Client")
    order = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-HANDOVER-002",
        status=ProductionJob.Status.QUEUED,
    )

    client = Client()
    assert client.login(email=staff_user.email, password="pass")
    response = client.post(
        reverse(
            "portal:staff-order-panel-production",
            kwargs={"order_public_id": order.public_id},
        ),
        {"action": "update_handover_date", "estimated_handover_date": "2026-09-18"},
    )

    assert response.status_code == 403


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
    assert "Recommander" not in panel.content.decode()
    assert "Visuels transmis" not in panel.content.decode()

    detail = upload_client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    assert "Recommander" in detail.content.decode()
    assert "client-order-reorder" in detail.content.decode()
