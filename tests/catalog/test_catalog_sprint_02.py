import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def create_client_scope(email: str, customer_name: str):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name)
    CustomerMembership.objects.create(customer=customer, user=user)

    client = APIClient()
    assert client.login(email=user.email, password="pass") is True
    return customer, client


def create_staff_client():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_catalogservice"),
    )

    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True
    return client


@pytest.mark.django_db
def test_client_catalog_route_returns_only_active_services_for_scoped_customer():
    customer, client = create_client_scope("client@example.com", "Acme")
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        display_order=1,
    )
    prep_service = CatalogService.objects.create(
        code="file-prep",
        name="Preparation de fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="19.00",
        display_order=2,
    )
    CatalogService.objects.create(
        code="inactive-service",
        name="Inactive service",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="5.00",
        is_active=False,
        display_order=3,
    )

    response = client.get(
        reverse(
            "catalog:client-service-list",
            kwargs={"customer_public_id": customer.public_id},
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "customer_public_id": str(customer.public_id),
        "services": [
            {
                "public_id": str(dtf_service.public_id),
                "code": "dtf-meter",
                "name": "DTF au metre",
                "description": "",
                "service_type": CatalogService.ServiceType.DTF_TRANSFER,
                "unit": CatalogService.Unit.LINEAR_METER,
                "pricing": {"base_price": "12.50", "currency": "EUR"},
            },
            {
                "public_id": str(prep_service.public_id),
                "code": "file-prep",
                "name": "Preparation de fichier",
                "description": "",
                "service_type": CatalogService.ServiceType.FILE_PREPARATION,
                "unit": CatalogService.Unit.FIXED,
                "pricing": {"base_price": "19.00", "currency": "EUR"},
            },
        ],
    }


@pytest.mark.django_db
def test_client_catalog_route_refuses_other_customer_scope():
    _, client = create_client_scope("client-a@example.com", "Acme A")
    customer_b = Customer.objects.create(name="Acme B")

    response = client.get(
        reverse(
            "catalog:client-service-list",
            kwargs={"customer_public_id": customer_b.public_id},
        )
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_catalog_route_includes_inactive_services():
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        is_active=True,
        display_order=1,
    )
    inactive_service = CatalogService.objects.create(
        code="file-prep",
        name="Preparation de fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="19.00",
        is_active=False,
        display_order=2,
    )
    staff_client = create_staff_client()

    response = staff_client.get(reverse("catalog:staff-service-list"))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert len(payload["services"]) == 2
    inactive_payload = next(
        service
        for service in payload["services"]
        if service["public_id"] == str(inactive_service.public_id)
    )
    assert inactive_payload["is_active"] is False
