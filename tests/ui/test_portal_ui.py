import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, override_settings
from django.urls import reverse


@pytest.mark.django_db
def test_client_portal_pages_and_panels_are_accessible_for_scoped_customer():
    user = get_user_model().objects.create_user(email="client-portal@example.com", password="pass")
    customer = Customer.objects.create(name="Client Portal")
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="42.00",
        total_amount="42.00",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")

    dashboard_response = client.get(reverse("portal:client-dashboard"))
    list_response = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer.public_id})
    )
    detail_response = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    uploads_panel_response = client.get(
        reverse(
            "portal:client-order-panel-uploads",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    inspection_panel_response = client.get(
        reverse(
            "portal:client-order-panel-inspection",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    production_panel_response = client.get(
        reverse(
            "portal:client-order-panel-production",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    shipping_panel_response = client.get(
        reverse(
            "portal:client-order-panel-shipping",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )
    billing_panel_response = client.get(
        reverse(
            "portal:client-order-panel-billing",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )

    assert dashboard_response.status_code == 200
    assert "Accueil client" in dashboard_response.content.decode()
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    assert uploads_panel_response.status_code == 200
    assert inspection_panel_response.status_code == 200
    assert production_panel_response.status_code == 200
    assert shipping_panel_response.status_code == 200
    assert billing_panel_response.status_code == 200


@pytest.mark.django_db
def test_client_user_cannot_access_other_customer_scope_in_portal():
    user = get_user_model().objects.create_user(email="client-scope@example.com", password="pass")
    customer_a = Customer.objects.create(name="Client A")
    customer_b = Customer.objects.create(name="Client B")
    CustomerMembership.objects.create(customer=customer_a, user=user)
    order_b = Order.objects.create(
        customer=customer_b,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="15.00",
        total_amount="15.00",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")

    list_response = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer_b.public_id})
    )
    detail_response = client.get(
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer_a.public_id,
                "order_public_id": order_b.public_id,
            },
        )
    )
    panel_response = client.get(
        reverse(
            "portal:client-order-panel-billing",
            kwargs={
                "customer_public_id": customer_b.public_id,
                "order_public_id": order_b.public_id,
            },
        )
    )

    assert list_response.status_code == 403
    assert detail_response.status_code == 404
    assert panel_response.status_code == 403


@pytest.mark.django_db
def test_client_user_cannot_access_staff_portal_routes():
    user = get_user_model().objects.create_user(email="client-only@example.com", password="pass")
    customer = Customer.objects.create(name="Scoped")
    CustomerMembership.objects.create(customer=customer, user=user)

    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(reverse("portal:staff-dashboard"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_portal_pages_and_panels_require_domain_permissions():
    staff_user = get_user_model().objects.create_user(
        email="staff-portal@example.com",
        password="pass",
        is_staff=True,
    )
    customer = Customer.objects.create(name="Customer A")
    order = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="12.00",
        total_amount="12.00",
    )

    required_permissions = [
        "access_staff_portal",
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "view_orderuploaddrivesync",
        "view_productionjob",
        "transition_productionjob",
        "scan_productionjob",
        "scan_transition_productionjob",
        "view_shipment",
        "view_payment",
        "view_invoice",
    ]
    for codename in required_permissions:
        staff_user.user_permissions.add(Permission.objects.get(codename=codename))

    client = Client()
    assert client.login(email=staff_user.email, password="pass")

    dashboard_response = client.get(reverse("portal:staff-dashboard"))
    list_response = client.get(reverse("portal:staff-order-list"))
    detail_response = client.get(
        reverse("portal:staff-order-detail", kwargs={"order_public_id": order.public_id})
    )
    production_panel_response = client.get(
        reverse("portal:staff-order-panel-production", kwargs={"order_public_id": order.public_id})
    )
    uploads_panel_response = client.get(
        reverse("portal:staff-order-panel-uploads", kwargs={"order_public_id": order.public_id})
    )
    inspections_panel_response = client.get(
        reverse("portal:staff-order-panel-inspection", kwargs={"order_public_id": order.public_id})
    )
    drive_panel_response = client.get(
        reverse("portal:staff-order-panel-drive-sync", kwargs={"order_public_id": order.public_id})
    )
    shipping_panel_response = client.get(
        reverse("portal:staff-order-panel-shipping", kwargs={"order_public_id": order.public_id})
    )
    scan_panel_response = client.get(
        reverse("portal:staff-order-panel-scan", kwargs={"order_public_id": order.public_id})
    )
    billing_panel_response = client.get(
        reverse("portal:staff-order-panel-billing", kwargs={"order_public_id": order.public_id})
    )

    assert dashboard_response.status_code == 200
    assert "Accueil staff" in dashboard_response.content.decode()
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    detail_html = detail_response.content.decode()
    assert "Synthèse commande staff" in detail_html
    assert "Prochaine action suggérée" in detail_html
    assert production_panel_response.status_code == 200
    assert uploads_panel_response.status_code == 200
    assert inspections_panel_response.status_code == 200
    assert drive_panel_response.status_code == 200
    assert shipping_panel_response.status_code == 200
    shipping_html = shipping_panel_response.content.decode()
    assert "État actuel" in shipping_html
    assert "Créer un envoi" in shipping_html
    assert "workflow-form-card" in shipping_html
    assert scan_panel_response.status_code == 200
    scan_html = scan_panel_response.content.decode()
    assert "Lecture atelier" in scan_html
    assert billing_panel_response.status_code == 200


@pytest.mark.django_db
def test_staff_without_order_permission_is_denied_on_staff_order_list():
    staff_user = get_user_model().objects.create_user(
        email="staff-denied@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))

    client = Client()
    assert client.login(email=staff_user.email, password="pass")

    response = client.get(reverse("portal:staff-order-list"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_without_billing_permissions_is_denied_on_staff_billing_panel():
    staff_user = get_user_model().objects.create_user(
        email="staff-no-billing@example.com",
        password="pass",
        is_staff=True,
    )
    customer = Customer.objects.create(name="Customer Billing")
    order = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="12.00",
        total_amount="12.00",
    )
    for codename in ("access_staff_portal", "view_order"):
        staff_user.user_permissions.add(Permission.objects.get(codename=codename))

    client = Client()
    assert client.login(email=staff_user.email, password="pass")

    response = client.get(
        reverse("portal:staff-order-panel-billing", kwargs={"order_public_id": order.public_id})
    )
    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(ORDER_LIST_PAGE_SIZE=2)
def test_client_order_list_is_paginated_in_portal():
    user = get_user_model().objects.create_user(email="client-pages@example.com", password="pass")
    customer = Customer.objects.create(name="Client Pages")
    CustomerMembership.objects.create(customer=customer, user=user)
    oldest = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    middle = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="20.00",
        total_amount="20.00",
    )
    newest = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="30.00",
        total_amount="30.00",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")

    first_page = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer.public_id})
    )
    second_page = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer.public_id}),
        {"page": 2},
    )

    first_html = first_page.content.decode()
    second_html = second_page.content.decode()
    assert first_page.status_code == 200
    assert str(newest.public_id) in first_html
    assert str(middle.public_id) in first_html
    assert str(oldest.public_id) not in first_html
    assert "Page 1 / 2" in first_html
    assert second_page.status_code == 200
    assert str(oldest.public_id) in second_html
    assert str(newest.public_id) not in second_html
    assert "Page 2 / 2" in second_html


@pytest.mark.django_db
@override_settings(STAFF_ORDER_LIST_PAGE_SIZE=2)
def test_staff_order_list_is_paginated_in_portal():
    staff_user = get_user_model().objects.create_user(
        email="staff-pages@example.com",
        password="pass",
        is_staff=True,
    )
    for codename in ("access_staff_portal", "view_order"):
        staff_user.user_permissions.add(Permission.objects.get(codename=codename))
    customer = Customer.objects.create(name="Staff Pages")
    oldest = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
    )
    middle = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="20.00",
        total_amount="20.00",
    )
    newest = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="30.00",
        total_amount="30.00",
    )

    client = Client()
    assert client.login(email=staff_user.email, password="pass")

    first_page = client.get(reverse("portal:staff-order-list"))
    second_page = client.get(reverse("portal:staff-order-list"), {"page": 2})

    first_html = first_page.content.decode()
    second_html = second_page.content.decode()
    assert first_page.status_code == 200
    assert str(newest.public_id) in first_html
    assert str(middle.public_id) in first_html
    assert str(oldest.public_id) not in first_html
    assert "Page 1 / 2" in first_html
    assert second_page.status_code == 200
    assert str(oldest.public_id) in second_html
    assert str(newest.public_id) not in second_html
    assert "Page 2 / 2" in second_html


@pytest.mark.django_db
def test_staff_price_endpoint_requires_change_order_permission():
    staff_user = get_user_model().objects.create_user(
        email="staff-no-change-order@example.com",
        password="pass",
        is_staff=True,
    )
    customer = Customer.objects.create(name="Customer Price")
    order = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
        billing_mode="deferred",
        pricing_status="pending",
    )
    for codename in ("access_staff_portal", "view_order"):
        staff_user.user_permissions.add(Permission.objects.get(codename=codename))

    client = Client()
    assert client.login(email=staff_user.email, password="pass")

    response = client.post(
        reverse("portal:staff-order-price", kwargs={"order_public_id": order.public_id}),
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_anonymous_portal_routes_redirect_to_portal_login():
    client = Client()

    response = client.get(reverse("portal:staff-dashboard"))
    assert response.status_code == 302
    assert reverse("portal:login") in response.url


@pytest.mark.django_db
def test_portal_login_redirects_to_role_appropriate_dashboard():
    user_model = get_user_model()
    client_user = user_model.objects.create_user(email="client-login@example.com", password="pass")
    customer = Customer.objects.create(name="Client Login")
    CustomerMembership.objects.create(customer=customer, user=client_user)

    staff_user = user_model.objects.create_user(
        email="staff-login@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))

    client = Client()
    client_response = client.post(
        reverse("portal:login"),
        {"username": client_user.email, "password": "pass"},
    )
    assert client_response.status_code == 302
    assert client_response.url == reverse("portal:client-dashboard")

    client.logout()

    staff_response = client.post(
        reverse("portal:login"),
        {"username": staff_user.email, "password": "pass"},
    )
    assert staff_response.status_code == 302
    assert staff_response.url == reverse("portal:staff-dashboard")


@pytest.mark.django_db
def test_login_page_shares_portal_navigation_shell():
    client = Client()
    response = client.get(reverse("portal:login"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "portal-primary-nav" in body
    assert "Accueil client" in body


@pytest.mark.django_db
def test_orders_table_shows_pending_label_when_not_priced():
    user = get_user_model().objects.create_user(email="pending-price@example.com", password="pass")
    customer = Customer.objects.create(name="Client Pending")
    CustomerMembership.objects.create(customer=customer, user=user)
    Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
        pricing_status=Order.PricingStatus.PENDING,
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    list_response = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer.public_id})
    )
    assert list_response.status_code == 200
    assert "En attente" in list_response.content.decode()
