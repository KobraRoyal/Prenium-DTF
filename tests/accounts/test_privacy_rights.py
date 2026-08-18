import json

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse


def _client_user(*, email: str, customer_name: str, role=CustomerMembership.Role.OWNER):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        first_name="Camille",
        last_name="Martin",
    )
    customer = Customer.objects.create(name=customer_name, billing_email=email)
    CustomerMembership.objects.create(customer=customer, user=user, role=role)
    return user, customer


@pytest.mark.django_db
def test_privacy_page_requires_authentication():
    response = Client().get(reverse("portal:privacy"))
    assert response.status_code == 302
    assert reverse("portal:login") in response.url


@pytest.mark.django_db
def test_user_can_export_own_data_without_leaking_another_tenant():
    user, customer = _client_user(email="owner-a@example.com", customer_name="Atelier A")
    other, other_customer = _client_user(email="owner-b@example.com", customer_name="Atelier B")
    Order.objects.create(customer=customer, created_by=user, source="test")
    Order.objects.create(customer=other_customer, created_by=other, source="test")

    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.post(reverse("portal:privacy-export"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")
    payload = json.loads(response.content.decode())
    assert payload["user"]["email"] == "owner-a@example.com"
    assert payload["customers"][0]["name"] == "Atelier A"
    exported_customer_ids = {item["public_id"] for item in payload["customers"]}
    assert str(other_customer.public_id) not in exported_customer_ids
    assert "owner-b@example.com" not in response.content.decode()
    assert len(payload["orders_created"]) == 1


@pytest.mark.django_db
def test_last_owner_closure_anonymizes_user_and_deactivates_organization():
    user, customer = _client_user(email="close-me@example.com", customer_name="Atelier Clos")
    client = Client()
    assert client.login(email=user.email, password="pass")

    page = client.get(reverse("portal:privacy"))
    assert page.status_code == 200
    assert "Clôturer mon compte" in page.content.decode()

    response = client.post(
        reverse("portal:privacy-close"),
        {"confirmation": "close-me@example.com", "space": "client"},
    )
    assert response.status_code == 302
    assert response.url == reverse("portal:account-closed")

    user.refresh_from_db()
    customer.refresh_from_db()
    assert user.is_active is False
    assert user.email.endswith("@invalid.localhost")
    assert user.first_name == "Anonymisé"
    assert customer.is_active is False
    assert not client.login(email="close-me@example.com", password="pass")
    assert AuditLogEntry.objects.filter(action="account.privacy.closed").exists()


@pytest.mark.django_db
def test_owner_closure_keeps_organization_when_another_owner_remains():
    user, customer = _client_user(email="owner-one@example.com", customer_name="Atelier Duo")
    other = get_user_model().objects.create_user(email="owner-two@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=other,
        role=CustomerMembership.Role.OWNER,
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.post(
        reverse("portal:privacy-close"),
        {"confirmation": "owner-one@example.com"},
    )
    assert response.status_code == 302
    customer.refresh_from_db()
    assert customer.is_active is True


@pytest.mark.django_db
def test_staff_cannot_self_close_account():
    user = get_user_model().objects.create_user(
        email="staff-close@example.com",
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client = Client()
    assert client.login(email=user.email, password="pass")
    page = client.get(f"{reverse('portal:privacy')}?space=staff")
    assert page.status_code == 200
    assert "Clôturer mon compte" not in page.content.decode()
    response = client.post(
        reverse("portal:privacy-close"),
        {"confirmation": "staff-close@example.com", "space": "staff"},
    )
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.is_active is True
    assert user.email == "staff-close@example.com"
