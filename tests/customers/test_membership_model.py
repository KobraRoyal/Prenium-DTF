import pytest
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.db import IntegrityError


@pytest.mark.django_db
def test_customer_membership_supports_multiple_users_per_customer():
    customer = Customer.objects.create(name="Acme")
    user_model = get_user_model()
    owner = user_model.objects.create_user(email="owner@example.com", password="pass")
    member = user_model.objects.create_user(email="member@example.com", password="pass")

    CustomerMembership.objects.create(
        customer=customer,
        user=owner,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=member,
        role=CustomerMembership.Role.MEMBER,
    )

    assert customer.memberships.count() == 2


@pytest.mark.django_db
def test_customer_membership_is_unique_per_customer_and_user():
    customer = Customer.objects.create(name="Acme")
    user = get_user_model().objects.create_user(email="contact@example.com", password="pass")

    CustomerMembership.objects.create(customer=customer, user=user)

    with pytest.raises(IntegrityError):
        CustomerMembership.objects.create(customer=customer, user=user)
