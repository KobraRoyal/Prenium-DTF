import pytest
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
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
def test_client_can_create_and_list_scoped_orders():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(customer=customer, user=user)
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )
    prep_service = CatalogService.objects.create(
        code="prep-file",
        name="Preparation fichier",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="25.00",
    )
    route = reverse(
        "orders:client-order-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )

    client = APIClient()
    client.login(email=user.email, password="pass")

    create_response = client.post(
        route,
        {
            "customer_note": "Premiere commande",
            "items": [
                {"service_public_id": str(dtf_service.public_id), "quantity": "2.50"},
                {"service_public_id": str(prep_service.public_id), "quantity": 1},
            ],
        },
        format="json",
    )

    assert create_response.status_code == status.HTTP_201_CREATED
    payload = create_response.json()
    assert payload["status"] == Order.Status.SUBMITTED
    assert payload["total_amount"] == "56.25"
    assert len(payload["items"]) == 2

    list_response = client.get(route)

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["customer_public_id"] == str(customer.public_id)
    assert len(list_response.json()["orders"]) == 1


@pytest.mark.django_db
def test_client_payload_cannot_override_server_side_pricing():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(customer=customer, user=user)
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )
    route = reverse(
        "orders:client-order-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )

    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.post(
        route,
        {
            "total_amount": "0.01",
            "items": [
                {
                    "service_public_id": str(dtf_service.public_id),
                    "quantity": "2.00",
                    "unit_price": "0.01",
                    "line_total": "0.01",
                }
            ],
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["total_amount"] == "25.00"
    assert payload["items"][0]["unit_price"] == "12.50"
    assert payload["items"][0]["line_total"] == "25.00"


@pytest.mark.django_db
def test_client_order_detail_is_scoped_to_customer():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    own_customer = Customer.objects.create(name="Own")
    other_customer = Customer.objects.create(name="Other")
    CustomerMembership.objects.create(customer=own_customer, user=user)
    service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )
    other_order = Order.objects.create(
        customer=other_customer,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="12.50",
        total_amount="12.50",
    )
    other_order.items.create(
        service=service,
        position=1,
        service_code=service.code,
        service_name=service.name,
        service_type=service.service_type,
        unit=service.unit,
        quantity="1.00",
        unit_price="12.50",
        line_total="12.50",
    )

    client = APIClient()
    client.login(email=user.email, password="pass")

    forbidden_response = client.get(
        reverse(
            "orders:client-order-detail",
            kwargs={
                "customer_public_id": other_customer.public_id,
                "order_public_id": other_order.public_id,
            },
        )
    )
    not_found_response = client.get(
        reverse(
            "orders:client-order-detail",
            kwargs={
                "customer_public_id": own_customer.public_id,
                "order_public_id": other_order.public_id,
            },
        )
    )

    assert forbidden_response.status_code == status.HTTP_403_FORBIDDEN
    assert not_found_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_staff_order_routes_are_separate_from_client_routes():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_order"),
    )
    customer = Customer.objects.create(name="Acme")
    order = Order.objects.create(
        customer=customer,
        created_by=staff_user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="25.00",
        total_amount="25.00",
    )

    staff_client = APIClient()
    staff_client.login(email=staff_user.email, password="pass")

    list_response = staff_client.get(reverse("orders:staff-order-list"))
    detail_response = staff_client.get(
        reverse("orders:staff-order-detail", kwargs={"order_public_id": order.public_id})
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["customer"]["public_id"] == str(customer.public_id)

    client_user = get_user_model().objects.create_user(email="client2@example.com", password="pass")
    client = APIClient()
    client.login(email=client_user.email, password="pass")

    denied_response = client.get(reverse("orders:staff-order-list"))

    assert_private_response_denied(denied_response)


@pytest.mark.django_db
def test_staff_order_routes_require_order_domain_permission():
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
    client.login(email=staff_user.email, password="pass")

    response = client.get(reverse("orders:staff-order-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
