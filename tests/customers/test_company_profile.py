import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.customers.services.company_profile import CompanyProfileService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

User = get_user_model()


def _scope(email: str, role: str, **customer_kwargs):
    user = User.objects.create_user(email=email, password="pass")
    payload = {
        "name": f"Org {email}",
        "billing_email": email,
        "siren": "123456789",
        "billing_address_line1": "10 rue de la Presse",
        "billing_postal_code": "75011",
        "billing_city": "Paris",
        "billing_country": "FR",
    }
    payload.update(customer_kwargs)
    customer = Customer.objects.create(**payload)
    membership = CustomerMembership.objects.create(customer=customer, user=user, role=role)
    return user, customer, membership


@pytest.mark.django_db
def test_profile_shows_company_information_for_client_space():
    user, customer, _membership = _scope(
        "owner-company@example.com",
        CustomerMembership.Role.OWNER,
        name="Atelier Nord",
        vat_number="FR123456789",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(f"{reverse('portal:profile')}?space=client")
    html = response.content.decode()

    assert response.status_code == 200
    assert "Société" in html
    assert "Atelier Nord" in html
    assert "123456789" in html
    assert "FR123456789" in html
    assert "10 rue de la Presse" in html
    assert "Identique à la facturation" in html
    assert "Modifier" in html
    assert (
        reverse(
            "portal:client-company-profile",
            kwargs={"customer_public_id": customer.public_id},
        )
        in html
    )


@pytest.mark.django_db
def test_member_sees_company_but_cannot_edit():
    owner, customer, _ = _scope("owner-co@example.com", CustomerMembership.Role.OWNER)
    member = User.objects.create_user(email="member-co@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=member,
        role=CustomerMembership.Role.MEMBER,
    )
    client = Client()
    assert client.login(email=member.email, password="pass")

    page = client.get(f"{reverse('portal:profile')}?space=client")
    html = page.content.decode()
    company_url = reverse(
        "portal:client-company-profile",
        kwargs={"customer_public_id": customer.public_id},
    )
    assert page.status_code == 200
    assert "Société" in html
    assert f"{company_url}?edit=1" not in html
    assert reverse("portal:profile-identity") in html
    assert "Seul un administrateur du compte peut modifier ces informations." in html

    edit = client.get(f"{company_url}?edit=1", HTTP_HX_REQUEST="true")
    assert edit.status_code == 403

    saved = client.post(
        company_url,
        {"name": "Intrusion", "billing_country": "FR", "shipping_country": "FR"},
        HTTP_HX_REQUEST="true",
    )
    assert saved.status_code == 403
    customer.refresh_from_db()
    assert customer.name != "Intrusion"


@pytest.mark.django_db
def test_admin_can_update_company_profile_via_htmx():
    user, customer, _ = _scope(
        "admin-co@example.com",
        CustomerMembership.Role.ADMIN,
        name="Ancien nom",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    url = reverse(
        "portal:client-company-profile",
        kwargs={"customer_public_id": customer.public_id},
    )

    form = client.get(f"{url}?edit=1", HTTP_HX_REQUEST="true")
    assert form.status_code == 200
    form_html = form.content.decode()
    assert 'name="name"' in form_html
    assert "Même adresse de livraison" in form_html

    response = client.post(
        url,
        {
            "name": "Studio Ouest",
            "billing_email": "facturation@ouest.example",
            "siren": "987654321",
            "vat_number": "FR987654321",
            "billing_address_line1": "5 avenue Hugo",
            "billing_address_line2": "",
            "billing_postal_code": "33000",
            "billing_city": "Bordeaux",
            "billing_country": "FR",
            "shipping_same_as_billing": "1",
            "shipping_address_line1": "ignore",
            "shipping_city": "ignore",
            "shipping_country": "BE",
        },
        HTTP_HX_REQUEST="true",
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "Studio Ouest" in html
    assert "5 avenue Hugo" in html
    assert "Identique à la facturation" in html
    assert "X-Prenium-Toast" in response.headers
    customer.refresh_from_db()
    assert customer.name == "Studio Ouest"
    assert customer.billing_email == "facturation@ouest.example"
    assert customer.siren == "987654321"
    assert customer.shipping_address_line1 == "5 avenue Hugo"
    assert customer.shipping_city == "Bordeaux"
    assert customer.shipping_country == "FR"
    audit = AuditLogEntry.objects.get(action="customer.company_profile.updated", actor=user)
    assert "name" in audit.metadata["fields"]
    assert "Studio Ouest" not in str(audit.metadata)


@pytest.mark.django_db
def test_company_profile_is_isolated_between_customers():
    _owner_a, customer_a, _ = _scope("a-co@example.com", CustomerMembership.Role.OWNER)
    owner_b, _customer_b, _ = _scope("b-co@example.com", CustomerMembership.Role.OWNER)
    client = Client()
    assert client.login(email=owner_b.email, password="pass")

    response = client.post(
        reverse(
            "portal:client-company-profile",
            kwargs={"customer_public_id": customer_a.public_id},
        ),
        {"name": "Piratage", "billing_country": "FR"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403
    customer_a.refresh_from_db()
    assert customer_a.name != "Piratage"


@pytest.mark.django_db
def test_apply_checkout_delivery_copies_billing_address():
    user, customer, _membership = _scope(
        "checkout-copy@example.com",
        CustomerMembership.Role.OWNER,
    )
    updated = CompanyProfileService().apply_checkout_delivery(
        customer=customer,
        actor=user,
        same_as_billing=True,
        source="test.studio_checkout",
    )
    assert updated.shipping_address_line1 == "10 rue de la Presse"
    assert updated.shipping_postal_code == "75011"
    assert updated.shipping_city == "Paris"
    assert updated.shipping_country == "FR"
    assert AuditLogEntry.objects.filter(action="customer.checkout_delivery.updated").exists()


@pytest.mark.django_db
def test_apply_checkout_delivery_requires_other_address():
    user, customer, _membership = _scope(
        "checkout-empty@example.com",
        CustomerMembership.Role.OWNER,
    )
    with pytest.raises(ValidationError, match="adresse de livraison"):
        CompanyProfileService().apply_checkout_delivery(
            customer=customer,
            actor=user,
            same_as_billing=False,
            payload={},
        )


@pytest.mark.django_db
def test_apply_checkout_delivery_writes_other_address():
    user, customer, _membership = _scope(
        "checkout-other@example.com",
        CustomerMembership.Role.OWNER,
    )
    updated = CompanyProfileService().apply_checkout_delivery(
        customer=customer,
        actor=user,
        same_as_billing=False,
        payload={
            "shipping_address_line1": "12 quai de Loire",
            "shipping_postal_code": "45000",
            "shipping_city": "Orléans",
            "shipping_country": "FR",
        },
    )
    assert updated.shipping_address_line1 == "12 quai de Loire"
    assert updated.shipping_city == "Orléans"
    assert updated.billing_address_line1 == "10 rue de la Presse"


@pytest.mark.django_db
def test_build_checkout_delivery_snapshot_requires_sendcloud_recipient():
    user, customer, _membership = _scope(
        "checkout-recipient@example.com",
        CustomerMembership.Role.OWNER,
    )
    customer.shipping_address_line1 = "quai de Loire"
    customer.shipping_postal_code = "45000"
    customer.shipping_city = "Orléans"
    customer.shipping_country = "FR"
    customer.save(
        update_fields=[
            "shipping_address_line1",
            "shipping_postal_code",
            "shipping_city",
            "shipping_country",
            "updated_at",
        ]
    )
    with pytest.raises(ValidationError, match="n° de voie"):
        CompanyProfileService().build_checkout_delivery_snapshot(
            customer=customer,
            payload={"name": customer.name, "email": customer.billing_email},
        )


@pytest.mark.django_db
def test_build_checkout_delivery_snapshot_keeps_sendcloud_fields():
    _user, customer, _membership = _scope(
        "checkout-snapshot@example.com",
        CustomerMembership.Role.OWNER,
    )
    customer.shipping_address_line1 = "quai de Loire"
    customer.shipping_postal_code = "45000"
    customer.shipping_city = "Orléans"
    customer.shipping_country = "FR"
    customer.save(
        update_fields=[
            "shipping_address_line1",
            "shipping_postal_code",
            "shipping_city",
            "shipping_country",
            "updated_at",
        ]
    )
    snapshot = CompanyProfileService().build_checkout_delivery_snapshot(
        customer=customer,
        payload={
            "name": "Marie Loire",
            "email": "marie@example.com",
            "phone": "0612345678",
            "company_name": "Atelier Loire",
            "house_number": "12",
        },
    )
    assert snapshot["line1"] == "quai de Loire"
    assert snapshot["house_number"] == "12"
    assert snapshot["name"] == "Marie Loire"
    assert snapshot["email"] == "marie@example.com"
    assert snapshot["phone"] == "0612345678"
