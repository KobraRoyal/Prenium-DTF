import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.services.orders import OrderService
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_marketing_pages_are_accessible_for_anonymous():
    CatalogService.objects.create(
        code="dtf-metre",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.00",
        currency="EUR",
        display_order=1,
    )

    client = Client()
    home = client.get(reverse("home"))
    services = client.get(reverse("services"))
    home_html = home.content.decode()

    assert home.status_code == 200
    assert "Parcours recommandé" in home_html
    assert "Commander" in home_html
    assert 'id="landing-services"' in home_html
    assert "Espace client" in home_html
    assert "DTF au metre" in home_html
    assert "id=\"landing-reassurance\"" in home_html
    assert "id=\"landing-why-us\"" in home_html
    assert "id=\"landing-services\"" in home_html
    assert "id=\"landing-how-it-works\"" in home_html
    assert "id=\"landing-quality\"" in home_html
    assert "id=\"landing-faq\"" in home_html
    assert "id=\"landing-cta-final\"" in home_html
    assert "Compte pro dédié" in home_html
    assert "Exemples d'usages" in home_html
    assert "Capsules" in home_html
    assert "meta name=\"description\"" in home_html
    assert services.status_code == 200
    services_html = services.content.decode()
    assert "Sélectionnez votre service" in services_html
    assert "demander un accès" in services_html.lower()
    assert "connectez-vous à votre espace" in services_html.lower()
    assert "Bénéfices métier" in services_html
    assert "Cas d’usage" in services_html
    assert "Réassurance" in services_html


@pytest.mark.django_db
def test_client_checkout_creates_order_in_scope():
    user = get_user_model().objects.create_user(email="checkout@example.com", password="pass")
    customer = Customer.objects.create(name="Client Checkout")
    CustomerMembership.objects.create(customer=customer, user=user)
    CatalogService.objects.create(
        code="prep-fichier",
        name="Preparation de fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="15.00",
        currency="EUR",
        display_order=1,
    )

    client = Client()
    assert client.login(email=user.email, password="pass")

    checkout_url = reverse(
        "portal:client-checkout",
        kwargs={"customer_public_id": customer.public_id},
    )
    response = client.post(
        checkout_url,
        {
            "customer_note": "Commande premium",
        },
    )

    assert response.status_code == 302
    assert "order=" in response.url
    order = OrderService().list_customer_orders(customer).first()
    assert order is not None
    assert order.source == "client_checkout"
    assert order.billing_mode == "deferred"
    assert order.status == "draft"


@pytest.mark.django_db
def test_client_checkout_upload_partial_updates_files_list():
    user = get_user_model().objects.create_user(
        email="checkout-upload@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Client Upload")
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    service = CatalogService.objects.create(
        code="dtf-upload",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="9.00",
        currency="EUR",
        display_order=1,
    )
    order = OrderService().create_order(
        customer=customer,
        actor=user,
        customer_membership=membership,
        items=[{"service_public_id": str(service.public_id), "quantity": "1"}],
        source="test_checkout",
    )

    client = Client()
    assert client.login(email=user.email, password="pass")
    upload_url = reverse(
        "portal:client-checkout-upload",
        kwargs={"customer_public_id": customer.public_id},
    )
    response = client.post(
        upload_url,
        {
            "order_public_id": str(order.public_id),
            "file": SimpleUploadedFile(
                "visuel.png",
                b"fake-image-content",
                content_type="image/png",
            ),
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert response.headers.get("HX-Trigger") == "checkoutUploadsUpdated"
    assert "visuel.png" in response.content.decode()


@pytest.mark.django_db
def test_client_checkout_rejects_cross_tenant_order_summary():
    user = get_user_model().objects.create_user(email="checkout-scope@example.com", password="pass")
    customer_a = Customer.objects.create(name="Client A")
    customer_b = Customer.objects.create(name="Client B")
    membership = CustomerMembership.objects.create(customer=customer_b, user=user)
    service = CatalogService.objects.create(
        code="dtf-scope",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        display_order=1,
    )
    order_b = OrderService().create_order(
        customer=customer_b,
        actor=user,
        customer_membership=membership,
        items=[{"service_public_id": str(service.public_id), "quantity": "1"}],
        source="test_scope",
    )
    CustomerMembership.objects.create(customer=customer_a, user=user)

    client = Client()
    assert client.login(email=user.email, password="pass")
    summary_url = reverse(
        "portal:client-checkout-summary",
        kwargs={"customer_public_id": customer_a.public_id},
    )
    response = client.get(summary_url, {"order": str(order_b.public_id)})

    assert response.status_code == 404


@pytest.mark.django_db
def test_client_checkout_b2b_submit_flow_goes_to_order_detail():
    """Parcours complet B2B : création draft → upload → soumission → fiche commande."""
    user = get_user_model().objects.create_user(email="b2b-flow@example.com", password="pass")
    customer = Customer.objects.create(name="Client B2B Flow")
    CustomerMembership.objects.create(customer=customer, user=user)

    client = Client()
    assert client.login(email=user.email, password="pass")

    checkout_url = reverse(
        "portal:client-checkout",
        kwargs={"customer_public_id": customer.public_id},
    )
    create_resp = client.post(checkout_url, {"customer_note": "Test parcours"})
    assert create_resp.status_code == 302
    order = OrderService().list_customer_orders(customer).first()
    assert order is not None
    assert order.status == "draft"

    upload_url = reverse(
        "portal:client-checkout-upload",
        kwargs={"customer_public_id": customer.public_id},
    )
    up_resp = client.post(
        upload_url,
        {
            "order_public_id": str(order.public_id),
            "quantity": "2",
            "support_color_hex": "#aabbcc",
            "file": SimpleUploadedFile(
                "fichier.png",
                b"\x89PNG\r\n\x1a\n",
                content_type="image/png",
            ),
        },
        HTTP_HX_REQUEST="true",
    )
    assert up_resp.status_code == 200

    submit_url = reverse(
        "portal:client-checkout-submit",
        kwargs={"customer_public_id": customer.public_id},
    )
    sub_resp = client.post(
        submit_url,
        {
            "order_public_id": str(order.public_id),
            "confirm_checkout": "on",
        },
    )
    assert sub_resp.status_code == 302
    detail_url = reverse(
        "portal:client-order-detail",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    assert sub_resp.url == detail_url

    order.refresh_from_db()
    assert order.status == "submitted"

    detail_resp = client.get(detail_url)
    assert detail_resp.status_code == 200
    body = detail_resp.content.decode()
    assert "Commande" in body
    assert "Suivez vos fichiers, la production, l'expédition et la facture" in body
