import pytest
from apps.accounts.services.access import AccessScopeService
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission


@pytest.mark.django_db
def test_access_scope_service_returns_staff_and_customer_scope():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="owner@example.com",
        password="pass",
        is_staff=True,
        staff_mfa_required=True,
    )
    permission = Permission.objects.get(codename="access_staff_portal")
    user.user_permissions.add(permission)
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )

    scope = AccessScopeService().get_user_scope(user)

    assert scope.is_authenticated is True
    assert scope.is_staff is True
    assert scope.has_staff_portal_access is True
    assert scope.customer_public_ids == (str(customer.public_id),)
    assert scope.memberships[0].role == CustomerMembership.Role.OWNER


@pytest.mark.django_db
def test_access_scope_service_checks_staff_domain_permissions_separately():
    user_model = get_user_model()
    user = user_model.objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_catalogservice"),
    )

    service = AccessScopeService()

    assert service.can_access_staff_domain(user, "catalog.view_catalogservice") is True
    assert service.can_access_staff_domain(user, "orders.view_order") is False
