import pytest
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model


@pytest.mark.django_db
def test_customer_queryset_for_user_only_returns_active_scope():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    visible_customer = Customer.objects.create(name="Visible Customer")
    inactive_membership_customer = Customer.objects.create(name="Inactive Membership Customer")
    inactive_customer = Customer.objects.create(name="Inactive Customer", is_active=False)

    CustomerMembership.objects.create(customer=visible_customer, user=user)
    CustomerMembership.objects.create(
        customer=inactive_membership_customer, user=user, is_active=False
    )
    CustomerMembership.objects.create(customer=inactive_customer, user=user)

    customers = list(Customer.objects.for_user(user))

    assert customers == [visible_customer]
