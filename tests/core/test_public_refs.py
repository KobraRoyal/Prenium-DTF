import uuid

import pytest
from apps.core.public_refs import short_public_ref
from apps.customers.models import Customer
from apps.orders.models import Order
from django.contrib.auth import get_user_model


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("dead7c70-1bda-49cc-983a-55576b264201", "55576b264201"),
        (uuid.UUID("dead7c70-1bda-49cc-983a-55576b264201"), "55576b264201"),
        ("55576b264201", "55576b264201"),
        ("", ""),
    ],
)
def test_short_public_ref_returns_last_uuid_segment(value, expected):
    assert short_public_ref(value) == expected


@pytest.mark.django_db
def test_order_short_ref_property():
    user = get_user_model().objects.create_user(email="ref@example.com", password="pass")
    customer = Customer.objects.create(name="Ref")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        public_id=uuid.UUID("dead7c70-1bda-49cc-983a-55576b264201"),
    )
    assert order.short_ref == "55576b264201"
