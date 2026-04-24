from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order, OrderLine
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
    return user, customer, client


def create_staff_client():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_order"),
    )

    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True
    return client


def create_service(*, code: str, unit: str, base_price: str, service_type: str):
    return CatalogService.objects.create(
        code=code,
        name=code.replace("-", " ").title(),
        service_type=service_type,
        unit=unit,
        base_price=base_price,
    )


def create_order(client: APIClient, customer, service, *, quantity, customer_note=""):
    return client.post(
        reverse(
            "orders:client-order-list-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        data={
            "items": [
                {
                    "service_public_id": str(service.public_id),
                    "quantity": quantity,
                }
            ],
            "customer_note": customer_note,
        },
        format="json",
    )


@pytest.mark.django_db
def test_client_can_create_minimal_order_with_customer_scope_and_audit():
    user, customer, client = create_client_scope("client@example.com", "Acme")
    service = create_service(
        code="dtf-meter",
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    )

    response = create_order(
        client,
        customer,
        service,
        quantity="3.00",
        customer_note="Urgent",
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()

    order = Order.objects.get(public_id=payload["public_id"])
    line = OrderLine.objects.get(order=order)
    audit_entry = AuditLogEntry.objects.get(
        action="order.created",
        target_public_id=order.public_id,
    )

    assert payload["customer_public_id"] == str(customer.public_id)
    assert payload["status"] == Order.Status.SUBMITTED
    assert payload["customer_note"] == "Urgent"
    assert payload["total_amount"] == "37.50"
    assert payload["items"] == [
        {
            "public_id": str(line.public_id),
            "service_public_id": str(service.public_id),
            "service_code": service.code,
            "service_name": service.name,
            "service_type": service.service_type,
            "unit": service.unit,
            "quantity": "3.00",
            "unit_price": "12.50",
            "line_total": "37.50",
        }
    ]
    assert order.customer == customer
    assert order.created_by == user
    assert order.total_amount == Decimal("37.50")
    assert line.service_code == service.code
    assert audit_entry.actor == user
    assert audit_entry.metadata["customer_public_id"] == str(customer.public_id)


@pytest.mark.django_db
def test_fixed_price_service_rejects_quantity_other_than_one():
    _, customer, client = create_client_scope("client@example.com", "Acme")
    service = create_service(
        code="file-prep",
        unit=CatalogService.Unit.FIXED,
        base_price="19.00",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
    )

    response = create_order(client, customer, service, quantity="2.00")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == ["Fixed-price services must use a quantity of 1."]
    assert Order.objects.count() == 0


@pytest.mark.django_db
def test_client_cannot_create_order_for_other_customer():
    _, _customer_a, client_a = create_client_scope("client-a@example.com", "Acme A")
    customer_b = Customer.objects.create(name="Acme B")
    service = create_service(
        code="dtf-meter",
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    )

    response = client_a.post(
        reverse(
            "orders:client-order-list-create",
            kwargs={"customer_public_id": customer_b.public_id},
        ),
        data={
            "items": [
                {
                    "service_public_id": str(service.public_id),
                    "quantity": "1.00",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_client_order_list_and_detail_are_scoped_to_customer():
    _, customer_a, client_a = create_client_scope("client-a@example.com", "Acme A")
    _, customer_b, client_b = create_client_scope("client-b@example.com", "Acme B")
    service = create_service(
        code="dtf-meter",
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    )

    response_a = create_order(client_a, customer_a, service, quantity="2.00")
    response_b = create_order(client_b, customer_b, service, quantity="1.00")

    assert response_a.status_code == status.HTTP_201_CREATED
    assert response_b.status_code == status.HTTP_201_CREATED

    order_a = response_a.json()
    order_b = response_b.json()

    list_response = client_a.get(
        reverse(
            "orders:client-order-list-create",
            kwargs={"customer_public_id": customer_a.public_id},
        )
    )
    detail_response = client_a.get(
        reverse(
            "orders:client-order-detail",
            kwargs={
                "customer_public_id": customer_a.public_id,
                "order_public_id": order_b["public_id"],
            },
        )
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["customer_public_id"] == str(customer_a.public_id)
    assert [order["public_id"] for order in list_response.json()["orders"]] == [
        order_a["public_id"]
    ]
    assert detail_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_authorized_staff_can_read_staff_order_routes():
    _, customer, client = create_client_scope("client@example.com", "Acme")
    service = create_service(
        code="dtf-meter",
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    )
    order_response = create_order(client, customer, service, quantity="1.00")
    staff_client = create_staff_client()

    assert order_response.status_code == status.HTTP_201_CREATED
    order_payload = order_response.json()

    list_response = staff_client.get(reverse("orders:staff-order-list"))
    detail_response = staff_client.get(
        reverse(
            "orders:staff-order-detail",
            kwargs={"order_public_id": order_payload["public_id"]},
        )
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_200_OK
    assert list_response.json()["orders"][0]["customer"] == {
        "public_id": str(customer.public_id),
        "name": customer.name,
    }
    assert detail_response.json()["customer"] == {
        "public_id": str(customer.public_id),
        "name": customer.name,
    }


@pytest.mark.django_db
def test_staff_without_permission_is_refused_from_staff_order_routes():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_client = APIClient()
    assert staff_client.login(email=staff_user.email, password="pass") is True

    response = staff_client.get(reverse("orders:staff-order-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_without_order_permission_is_refused_even_with_staff_portal_access():
    staff_user = get_user_model().objects.create_user(
        email="staff-portal@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    staff_client = APIClient()
    assert staff_client.login(email=staff_user.email, password="pass") is True

    response = staff_client.get(reverse("orders:staff-order-list"))

    assert response.status_code == status.HTTP_403_FORBIDDEN
