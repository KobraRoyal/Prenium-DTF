import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def assert_private_response_denied(response):
    assert response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }


@pytest.mark.django_db
def test_client_catalog_list_returns_only_active_services_for_scoped_customer():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(customer=customer, user=user)
    active_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        display_order=1,
    )
    CatalogService.objects.create(
        code="prep-file",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="25.00",
        display_order=2,
        is_active=False,
    )

    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.get(
        reverse("catalog:client-service-list", kwargs={"customer_public_id": customer.public_id})
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "customer_public_id": str(customer.public_id),
        "services": [
            {
                "public_id": str(active_service.public_id),
                "code": "dtf-meter",
                "name": "DTF au metre",
                "description": "",
                "service_type": CatalogService.ServiceType.DTF_TRANSFER,
                "unit": CatalogService.Unit.LINEAR_METER,
                "pricing": {"base_price": "12.50", "currency": "EUR"},
            }
        ],
    }


@pytest.mark.django_db
def test_client_catalog_list_is_refused_outside_customer_scope():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    own_customer = Customer.objects.create(name="Own")
    other_customer = Customer.objects.create(name="Other")
    CustomerMembership.objects.create(customer=own_customer, user=user)

    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.get(
        reverse(
            "catalog:client-service-list",
            kwargs={"customer_public_id": other_customer.public_id},
        )
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_catalog_list_is_separate_from_client_access():
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        is_active=True,
    )
    inactive_service = CatalogService.objects.create(
        code="prep-file",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="25.00",
        is_active=False,
    )
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_catalogservice"),
    )

    staff_client = APIClient()
    staff_client.login(email=staff_user.email, password="pass")

    response = staff_client.get(reverse("catalog:staff-service-list"))

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["services"][1]["public_id"] == str(inactive_service.public_id)
    assert response.json()["services"][1]["is_active"] is False

    client_user = get_user_model().objects.create_user(email="client2@example.com", password="pass")
    client = APIClient()
    client.login(email=client_user.email, password="pass")

    denied_response = client.get(reverse("catalog:staff-service-list"))

    assert_private_response_denied(denied_response)


@pytest.mark.django_db
def test_staff_catalog_list_requires_catalog_domain_permission():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_order"),
    )

    staff_client = APIClient()
    staff_client.login(email=staff_user.email, password="pass")

    response = staff_client.get(reverse("catalog:staff-service-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
