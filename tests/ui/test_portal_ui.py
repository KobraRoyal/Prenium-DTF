from pathlib import Path

import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client, override_settings
from django.urls import reverse


@pytest.mark.django_db
def test_client_portal_pages_and_panels_are_accessible_for_scoped_customer():
    user = get_user_model().objects.create_user(email="client-portal@example.com", password="pass")
    customer = Customer.objects.create(name="Client Portal")
    CustomerMembership.objects.create(
        customer=customer, user=user, role=CustomerMembership.Role.OWNER
    )
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
    dashboard_html = dashboard_response.content.decode()
    assert "Commandes à finaliser et commandes transmises" in dashboard_html
    assert "product-shell--portal" in dashboard_html
    assert "client-dashboard" in dashboard_html
    assert "Commandes transmises" in dashboard_html
    assert "Accès isolé" not in dashboard_html
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    detail_html = detail_response.content.decode()
    assert "client-order-detail" in detail_html
    assert "client-order-summary" in detail_html
    assert "client-order-summary__facts" in detail_html
    assert "Commande soumise" in detail_html
    assert 'role="tablist"' in detail_html
    assert "client-order-panel" in detail_html
    assert "N° IDS" in detail_html
    assert "Votre réf." in detail_html
    assert "Visuels" in detail_html
    assert "Contrôle" not in detail_html
    assert uploads_panel_response.status_code == 200
    uploads_html = uploads_panel_response.content.decode()
    assert "Visuels transmis" in uploads_html
    assert "client-order-panel--uploads" in uploads_html
    assert inspection_panel_response.status_code == 200
    assert production_panel_response.status_code == 200
    assert shipping_panel_response.status_code == 200
    assert billing_panel_response.status_code == 200


@pytest.mark.django_db
@override_settings(B2B_ORDER_PROJECTS_ENABLED=True)
def test_client_navigation_only_shows_planche_tools_for_eligible_customer():
    user = get_user_model().objects.create_user(
        email="client-navigation@example.com", password="pass"
    )
    customer = Customer.objects.create(name="Navigation client", b2b_order_projects_enabled=False)
    CustomerMembership.objects.create(
        customer=customer, user=user, role=CustomerMembership.Role.OWNER
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="15.00",
        total_amount="15.00",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    disabled_html = client.get(reverse("portal:client-dashboard")).content.decode()
    assert "Dashboard" in disabled_html
    assert "Créer une commande" in disabled_html
    assert "Planches DTF" not in disabled_html
    assert "Générer une Gang Sheet" not in disabled_html

    customer.b2b_order_projects_enabled = True
    customer.save(update_fields=["b2b_order_projects_enabled"])

    enabled_html = client.get(reverse("portal:client-dashboard")).content.decode()
    assert "Planches DTF" not in enabled_html
    assert "À partir de fichiers" in enabled_html
    assert "Générer une Gang Sheet" in enabled_html
    assert "product-profile__trigger" in enabled_html
    assert "Mon compte" in enabled_html
    assert "Propriétaire · Navigation client" in enabled_html
    assert "Gérer l’équipe" in enabled_html
    assert "Ouvrir l’Atelier" not in enabled_html
    assert "Se déconnecter" in enabled_html

    owner_urls = [
        reverse("portal:client-dashboard"),
        reverse(
            "portal:client-order-list",
            kwargs={"customer_public_id": customer.public_id},
        ),
        reverse(
            "portal:client-order-project-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
            },
        ),
        reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
    ]
    for url in owner_urls:
        response = client.get(url)
        assert response.status_code == 200
        page_html = response.content.decode()
        assert page_html.count("Gérer l’équipe") == 1
        assert "Propriétaire · Navigation client" in page_html
        assert "À partir de fichiers" in page_html
        assert "Générer une Gang Sheet" in page_html

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client.logout()
    assert client.login(email=user.email, password="pass")

    hybrid_html = client.get(reverse("portal:client-dashboard")).content.decode()
    assert "Ouvrir l’Atelier" in hybrid_html
    assert "Passer au pilotage opérationnel" in hybrid_html


@pytest.mark.django_db
def test_staff_navigation_groups_only_authorized_secondary_tools():
    staff_user = get_user_model().objects.create_user(
        email="staff-navigation@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client = Client()
    assert client.login(email=staff_user.email, password="pass")

    limited_html = client.get(reverse("portal:staff-dashboard")).content.decode()
    assert "Dashboard" in limited_html
    assert "Commandes" in limited_html
    assert "Mon compte" in limited_html
    assert "Équipe Atelier" in limited_html
    assert "Mes informations" in limited_html
    assert "Voir le site" not in limited_html
    assert "Gérer l’équipe" not in limited_html
    assert "Outils Atelier" not in limited_html
    assert "Modèles d’e-mails" not in limited_html

    staff_user.user_permissions.add(Permission.objects.get(codename="view_emailtemplate"))

    authorized_html = client.get(reverse("portal:staff-dashboard")).content.decode()
    assert "Outils Atelier" in authorized_html
    assert "Modèles d’e-mails" in authorized_html
    assert "Demandes d’accès" not in authorized_html
    assert "Réglages de laize" not in authorized_html


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
    dashboard_html = dashboard_response.content.decode()
    assert "File Atelier" in dashboard_html
    assert "product-shell--portal" in dashboard_html
    assert "Commandes Atelier" in dashboard_html
    assert 'role="tablist"' in dashboard_html
    assert "Prêts à imprimer" in dashboard_html
    assert "Imprimer les 5 derniers OF prêts" in dashboard_html
    assert "Contrats permissions" not in dashboard_html
    assert "Accès commandes autorisé" not in dashboard_html
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    detail_html = detail_response.content.decode()
    assert "staff-order-focus" in detail_html
    assert "Prochaine action" in detail_html
    assert "Aucun visuel reçu" in detail_html
    assert "Client &amp; références" not in detail_html
    assert "Workflow commande" not in detail_html
    assert ">Fichiers<" not in detail_html
    assert "Incident Drive" not in detail_html
    assert "tab_icon" not in detail_html
    assert "/panels/inspection/" in detail_html
    assert "Valider les fichiers" in detail_html
    assert "Tracer l&#x27;avancement" in detail_html
    assert "Retour à la file" in detail_html
    assert production_panel_response.status_code == 200
    production_html = production_panel_response.content.decode()
    assert "data-submit-loading" in production_html
    assert "Avancement de l’OF" in production_html
    assert '<option value="in_progress">' in production_html
    assert '<option value="blocked">' in production_html
    assert '<option value="ready_to_ship">' not in production_html
    assert uploads_panel_response.status_code == 200
    assert inspections_panel_response.status_code == 200
    assert drive_panel_response.status_code == 200
    assert shipping_panel_response.status_code == 200
    shipping_html = shipping_panel_response.content.decode()
    assert "Terminez la production avant de créer l’envoi" in shipping_html
    assert "Consultation seule" in shipping_html
    assert "Générer l’étiquette" not in shipping_html
    assert scan_panel_response.status_code == 200
    scan_html = scan_panel_response.content.decode()
    assert "Lecture immédiate" in scan_html
    assert "Utiliser l’OF de cette commande" in scan_html
    assert "$refs.scanInput.focus({ preventScroll: true })" in scan_html
    assert "data-submit-loading" in scan_html
    assert billing_panel_response.status_code == 200
    billing_html = billing_panel_response.content.decode()
    assert "workflow-panel" in billing_html
    assert "Synthèse de facturation" in billing_html
    assert "Pièces de la commande" in billing_html


@pytest.mark.django_db
def test_shipping_panel_is_prefilled_only_when_workflow_and_permission_allow_creation():
    staff_user = get_user_model().objects.create_user(
        email="shipping-operator@example.com",
        password="pass",
        is_staff=True,
    )
    customer = Customer.objects.create(
        name="Atelier Client",
        billing_email="logistique@example.com",
        shipping_address_line1="Rue des Imprimeurs",
        shipping_address_line2="Bâtiment B",
        shipping_postal_code="59000",
        shipping_city="Lille",
        shipping_country="FR",
    )
    order = Order.objects.create(customer=customer, created_by=staff_user)
    ProductionJob.objects.create(
        order=order,
        manufacturing_order_number="OF-TEST-SHIPPING",
        scan_identifier="OF-TEST-SHIPPING",
        status=ProductionJob.Status.READY_TO_SHIP,
    )
    for codename in ("access_staff_portal", "view_order", "view_shipment", "create_shipment"):
        staff_user.user_permissions.add(Permission.objects.get(codename=codename))

    client = Client()
    assert client.login(email=staff_user.email, password="pass")
    panel_url = reverse(
        "portal:staff-order-panel-shipping", kwargs={"order_public_id": order.public_id}
    )
    response = client.get(panel_url)

    assert response.status_code == 200
    html = response.content.decode()
    assert "La production est prête à expédier" in html
    assert 'value="Atelier Client"' in html
    assert 'value="logistique@example.com"' in html
    assert 'value="Rue des Imprimeurs"' in html
    assert 'value="59000"' in html
    assert "Générer l’étiquette" in html

    invalid_response = client.post(
        panel_url,
        {
            "shipping_option_code": "",
            "recipient_name": "Valeur conservée",
            "recipient_email": "retained@example.com",
            "recipient_country_code": "FR",
            "recipient_city": "Lille",
            "recipient_postal_code": "59000",
            "recipient_address_line_1": "Rue des Imprimeurs",
            "recipient_house_number": "12",
            "parcel_weight_value": "1.25",
        },
        HTTP_HX_REQUEST="true",
    )

    assert invalid_response.status_code == 200
    invalid_html = invalid_response.content.decode()
    assert 'value="Valeur conservée"' in invalid_html
    assert 'value="retained@example.com"' in invalid_html
    assert 'value="1.25"' in invalid_html
    assert "alert--danger" in invalid_html


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
def test_client_order_list_supports_htmx_search():
    user = get_user_model().objects.create_user(email="client-search@example.com", password="pass")
    customer = Customer.objects.create(name="Client Search")
    CustomerMembership.objects.create(customer=customer, user=user)
    alpha = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="10.00",
        total_amount="10.00",
        customer_note="Collection Alpha",
    )
    Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="20.00",
        total_amount="20.00",
        customer_note="Collection Beta",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    list_url = reverse(
        "portal:client-order-list",
        kwargs={"customer_public_id": customer.public_id},
    )

    page = client.get(list_url)
    assert page.status_code == 200
    assert 'id="client-orders-search-input"' in page.content.decode()

    partial = client.get(list_url, {"q": "Alpha"}, HTTP_HX_REQUEST="true")
    html = partial.content.decode()
    assert partial.status_code == 200
    assert str(alpha.public_id) in html
    assert "Collection Beta" not in html
    assert "ui-orders-table-desktop" in html
    assert "<html" not in html.lower()


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
def test_login_page_uses_minimal_brand_shell_without_internal_roles():
    client = Client()
    response = client.get(reverse("portal:login"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "product-shell--auth" in body
    assert "ui-brand-lockup__mark" in body
    assert "Retour au site" in body
    assert "Email professionnel" in body
    assert "Retrouvez vos commandes, vos fichiers et vos documents" in body
    assert "Demander un accès professionnel" in body
    assert "data-product-menu-toggle" not in body
    assert "portal-primary-nav" not in body
    assert "Commandes et fichiers" not in body
    assert "Ops et production" not in body
    assert "Une seule porte d’entrée" not in body


def test_portal_feedback_js_uses_text_nodes_for_local_messages():
    repo_root = Path(__file__).resolve().parents[2]
    feedback_js = repo_root / "backend" / "static_src" / "js" / "htmx" / "feedback.js"
    source = feedback_js.read_text()
    assert "text.textContent = message" in source
    assert "box.innerHTML" not in source


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
