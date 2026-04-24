import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_order_routes_remain_scoped_after_uploads_app_is_added():
    user_a = get_user_model().objects.create_user(email="a@example.com", password="pass")
    user_b = get_user_model().objects.create_user(email="b@example.com", password="pass")
    customer_a = Customer.objects.create(name="Acme A")
    customer_b = Customer.objects.create(name="Acme B")
    CustomerMembership.objects.create(customer=customer_a, user=user_a)
    CustomerMembership.objects.create(customer=customer_b, user=user_b)
    order_a = Order.objects.create(
        customer=customer_a,
        created_by=user_a,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="12.50",
        total_amount="12.50",
    )
    order_b = Order.objects.create(
        customer=customer_b,
        created_by=user_b,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="12.50",
        total_amount="12.50",
    )

    client = APIClient()
    assert client.login(email=user_a.email, password="pass") is True

    own_detail = client.get(
        reverse(
            "orders:client-order-detail",
            kwargs={
                "customer_public_id": customer_a.public_id,
                "order_public_id": order_a.public_id,
            },
        )
    )
    foreign_detail = client.get(
        reverse(
            "orders:client-order-detail",
            kwargs={
                "customer_public_id": customer_b.public_id,
                "order_public_id": order_b.public_id,
            },
        )
    )

    assert own_detail.status_code == status.HTTP_200_OK
    assert foreign_detail.status_code == status.HTTP_403_FORBIDDEN
