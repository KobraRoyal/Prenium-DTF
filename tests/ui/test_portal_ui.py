from decimal import Decimal
from pathlib import Path

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer, CustomerMembership, CustomerVolumeDiscountTier
from apps.orders.models import Order
from apps.production.models import ProductionJob
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
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
        ),
        HTTP_HX_REQUEST="true",
    )
    billing_full_page = client.get(
        reverse(
            "portal:client-order-panel-billing",
            kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
        )
    )

    assert dashboard_response.status_code == 200
    dashboard_html = dashboard_response.content.decode()
    assert "product-shell--portal" in dashboard_html
    assert "client-dashboard" in dashboard_html
    assert 'data-testid="client-dashboard-focus"' in dashboard_html
    assert "Accès isolé" not in dashboard_html
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    detail_html = detail_response.content.decode()
    assert "client-order-detail" in detail_html
    assert "client-order-summary" in detail_html
    assert "client-order-summary__facts" in detail_html
    assert "Soumise" in detail_html
    assert 'role="tablist"' in detail_html
    assert "client-order-panel" in detail_html
    assert "Visuels" in detail_html
    assert "Contrôle" not in detail_html
    assert uploads_panel_response.status_code == 200
    uploads_html = uploads_panel_response.content.decode()
    assert "client-order-panel--uploads" in uploads_html
    assert "Visuels transmis" not in uploads_html
    assert inspection_panel_response.status_code == 200
    assert production_panel_response.status_code == 200
    assert shipping_panel_response.status_code == 200
    assert billing_panel_response.status_code == 200
    assert billing_full_page.status_code == 302
    assert "panel=billing" in billing_full_page["Location"]
    assert "/panels/billing/" not in billing_full_page["Location"]


@pytest.mark.django_db
def test_client_dashboard_shows_only_scoped_customer_volume_tier():
    user = get_user_model().objects.create_user(
        email="volume-dashboard@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Mon atelier", default_billing_mode="deferred")
    other_customer = Customer.objects.create(name="Atelier voisin", default_billing_mode="deferred")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("10.0000"),
        discount_percent=Decimal("5.00"),
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=other_customer,
        minimum_monthly_linear_m=Decimal("1.0000"),
        discount_percent=Decimal("99.00"),
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(reverse("portal:client-dashboard"))

    assert response.status_code == 200
    html = response.content.decode()
    assert 'data-testid="client-volume-discount-summary"' in html
    assert "Encore 10 m pour -5 %" in html
    assert "Le palier s’applique à tout le DTF du mois." in html
    assert html.count("10 m") == 1
    assert "Avantage mensuel" not in html
    assert "Remise actuelle" not in html
    assert "99,00 %" not in html
    assert "99.00 %" not in html
    assert "Appliquée à tout le DTF éligible du mois" not in html


@pytest.mark.django_db
def test_client_dashboard_cash_volume_copy_and_empty_lists():
    user = get_user_model().objects.create_user(
        email="volume-dashboard-cash@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Atelier comptant",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    html = client.get(reverse("portal:client-dashboard")).content.decode()

    assert "Encore 5 m pour -10 %" in html
    assert "sans rétroactivité" in html
    assert "déjà sur le tapis" not in html
    assert "Préparer une commande DTF" not in html
    assert "Importez vos visuels" not in html
    assert "en encours non relevées" not in html
    assert "Commandes transmises" not in html
    assert "Aucune commande transmise" not in html
    assert "Nouvelle commande" not in html


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_client_dashboard_does_not_repeat_focused_project_in_list():
    user = get_user_model().objects.create_user(
        email="dashboard-focus-once@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Atelier unique")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number="CMD-2026-000084",
        name="Planche unique",
        status=B2BOrderProject.Status.READY_TO_SUBMIT,
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    html = client.get(reverse("portal:client-dashboard")).content.decode()

    assert html.count("CMD-2026-000084") == 1
    assert 'data-testid="client-dashboard-focus"' in html
    assert "Reprendre" in html
    assert "Commandes à finaliser" not in html
    assert "visuel(s)" not in html


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_client_navigation_shows_project_creation_for_all_active_customers():
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

    enabled_html = client.get(reverse("portal:client-dashboard")).content.decode()
    assert "Tableau de bord" in enabled_html
    assert "Créer une commande" in enabled_html
    assert "Planches DTF" in enabled_html
    assert "À partir de fichiers" in enabled_html
    assert "Composer une planche DTF" in enabled_html
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
        assert "Composer une planche DTF" in page_html
        assert "Planches DTF" in page_html

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client.logout()
    assert client.login(email=user.email, password="pass")

    hybrid_html = client.get(reverse("portal:client-dashboard")).content.decode()
    assert "Ouvrir l’Atelier" in hybrid_html
    assert "Passer au pilotage opérationnel" in hybrid_html


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=False)
def test_client_navigation_falls_back_to_classic_checkout_when_projects_disabled():
    user = get_user_model().objects.create_user(
        email="client-checkout-fallback@example.com", password="pass"
    )
    customer = Customer.objects.create(name="Checkout fallback")
    CustomerMembership.objects.create(
        customer=customer, user=user, role=CustomerMembership.Role.OWNER
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    html = client.get(reverse("portal:client-dashboard")).content.decode()
    assert "Créer une commande" in html
    assert "À partir de fichiers" not in html
    assert "Composer une planche DTF" not in html
    assert "Planches DTF" not in html
    assert (
        reverse("portal:client-checkout", kwargs={"customer_public_id": customer.public_id}) in html
    )


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
    assert "Tableau de bord" in limited_html
    assert "Commandes" in limited_html
    assert "Mon compte" in limited_html
    assert "Équipe Atelier" in limited_html
    assert "Mes informations" in limited_html
    assert "Voir le site" not in limited_html
    assert "Gérer l’équipe" not in limited_html
    assert "Réglages" not in limited_html
    assert "Modèles d’e-mails" not in limited_html

    staff_user.user_permissions.add(Permission.objects.get(codename="view_emailtemplate"))

    authorized_html = client.get(reverse("portal:staff-dashboard")).content.decode()
    assert "Réglages" in authorized_html
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
        billing_mode=Order.BillingMode.DEFERRED,
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
    operations_response = client.get(reverse("portal:staff-atelier-operations"))
    scan_panel_response = client.get(
        reverse("portal:staff-order-panel-scan", kwargs={"order_public_id": order.public_id})
    )
    billing_panel_response = client.get(
        reverse("portal:staff-order-panel-billing", kwargs={"order_public_id": order.public_id})
    )

    assert dashboard_response.status_code == 200
    dashboard_html = dashboard_response.content.decode()
    assert "Tableau de bord" in dashboard_html
    assert "ui-kpi-grid" in dashboard_html
    assert "OF non imprimés" in dashboard_html
    assert "product-shell--portal" in dashboard_html
    assert "Filtrer la file Atelier" not in dashboard_html
    assert "Imprimer le lot" in dashboard_html
    assert "Prochain geste" not in dashboard_html
    assert "atelier-next-action" not in dashboard_html
    assert "Contrats permissions" not in dashboard_html
    assert "Accès commandes autorisé" not in dashboard_html
    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    detail_html = detail_response.content.decode()
    assert "page-head" in detail_html
    assert "staff-order-detail-identity" in detail_html
    assert "staff-order-focus__facts" in detail_html
    assert "atelier-next-action" not in detail_html
    assert "Prochain geste" not in detail_html
    assert "Aucun visuel reçu" in detail_html
    assert "Client &amp; références" not in detail_html
    assert "Workflow commande" not in detail_html
    assert ">Fichiers<" not in detail_html
    assert "Incident Drive" not in detail_html
    assert "tab_icon" not in detail_html
    assert "/panels/inspection/" in detail_html
    assert "Valider les fichiers" not in detail_html
    assert "Tracer l&#x27;avancement" not in detail_html
    assert "Scan atelier" not in detail_html
    assert "/panels/scan/" not in detail_html
    assert "Retour à la file" not in detail_html
    assert production_panel_response.status_code == 200
    production_html = production_panel_response.content.decode()
    assert "data-submit-loading" in production_html
    assert "Avancement de l’OF" not in production_html
    assert "operator-reference-bar" not in production_html
    assert "Métrage de production" in production_html
    assert '<option value="in_progress">' in production_html
    assert '<option value="blocked">' in production_html
    assert '<option value="ready_to_ship">' not in production_html
    assert uploads_panel_response.status_code == 200
    assert inspections_panel_response.status_code == 200
    assert drive_panel_response.status_code == 200
    assert shipping_panel_response.status_code == 200
    shipping_html = shipping_panel_response.content.decode()
    assert "Disponible quand l’OF sera prêt à expédier" in shipping_html
    assert "Consultation seule" in shipping_html
    assert "Générer l’étiquette" not in shipping_html
    assert "Déclarer dans Sendcloud" not in shipping_html
    assert operations_response.status_code == 200
    operations_html = operations_response.content.decode()
    assert "Pilotage Atelier" in operations_html
    assert "N° ordre de fabrication" in operations_html
    assert "Scanner un OF" in operations_html
    assert scan_panel_response.status_code == 302
    assert reverse("portal:staff-atelier-operations") in scan_panel_response["Location"]
    assert billing_panel_response.status_code == 200
    billing_html = billing_panel_response.content.decode()
    assert "workflow-panel" in billing_html
    assert "Montant et mode de facturation" in billing_html
    assert "Détail du montant" in billing_html
    assert "Pièces de la commande" not in billing_html


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
    assert "Prêt à déclarer" in html
    assert "Vérifiez le destinataire et le poids" in html
    assert 'value="Atelier Client"' in html
    assert 'value="logistique@example.com"' in html
    assert 'value="Rue des Imprimeurs"' in html
    assert 'value="59000"' in html
    assert "Déclarer dans Sendcloud" in html

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
            "recipient_house_number": "",
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
    assert 'id="id_username-error" role="alert" hidden' in body
    assert 'id="id_password-error" role="alert" hidden' in body
    assert "novalidate" in body
    assert "data-inline-required" in body


@pytest.mark.django_db
def test_login_empty_fields_show_inline_errors_not_credentials_banner():
    cache.clear()
    client = Client()
    response = client.post(reverse("portal:login"), {"username": "", "password": ""})
    assert response.status_code == 200
    body = response.content.decode()
    assert 'id="id_username-error" role="alert">Indiquez votre email professionnel.</p>' in body
    assert 'id="id_password-error" role="alert">Indiquez votre mot de passe.</p>' in body
    assert "ui-input--error" in body
    assert "Email ou mot de passe incorrect" not in body


@pytest.mark.django_db
def test_login_wrong_password_shows_banner_not_missing_field_copy():
    cache.clear()
    get_user_model().objects.create_user(
        email="login-miss@example.com",
        password="pass1234",
    )
    client = Client()
    response = client.post(
        reverse("portal:login"),
        {"username": "login-miss@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 200
    body = response.content.decode()
    assert "Email ou mot de passe incorrect. Vérifiez vos informations puis réessayez." in body
    assert 'id="id_username-error" role="alert" hidden' in body
    assert 'id="id_password-error" role="alert" hidden' in body
    assert "alert--danger" in body


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


@pytest.mark.django_db
def test_orders_table_and_dashboard_show_unpaid_payment_flag():
    from decimal import Decimal

    from apps.uploads.models import OrderUpload, OrderUploadInspection
    from django.core.files.base import ContentFile

    user = get_user_model().objects.create_user(email="unpaid-flag@example.com", password="pass")
    customer = Customer.objects.create(
        name="Client Unpaid",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PRICED,
        source="client_portal.b2b_checkout",
        currency="EUR",
        subtotal_amount=Decimal("40.00"),
        total_amount=Decimal("40.00"),
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="u.png",
        mime_type="image/png",
        size_bytes=4,
        quantity=1,
    )
    upload.file.save("u.png", ContentFile(b"data"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=100,
        image_height=100,
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    list_response = client.get(
        reverse("portal:client-order-list", kwargs={"customer_public_id": customer.public_id})
    )
    assert list_response.status_code == 200
    list_body = list_response.content.decode()
    assert "Paiement non finalisé" in list_body
    assert "Payer" in list_body
    assert "panel=billing&amp;pay=1" in list_body or "panel=billing&pay=1" in list_body

    dash_response = client.get(reverse("portal:client-dashboard"))
    assert dash_response.status_code == 200
    dash_body = dash_response.content.decode()
    assert "Paiement à finaliser" in dash_body
    assert "Payer" in dash_body
    assert dash_body.lower().count("paiement") >= 1
    assert "Commandes transmises" not in dash_body
