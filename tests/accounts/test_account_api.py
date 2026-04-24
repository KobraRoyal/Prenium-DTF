import pytest
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
def test_anonymous_user_is_refused_from_private_routes():
    customer = Customer.objects.create(name="Acme")
    client = APIClient()

    routes = [
        reverse("accounts:client-me"),
        reverse(
            "accounts:client-customer-detail", kwargs={"customer_public_id": customer.public_id}
        ),
        reverse("accounts:staff-me"),
    ]

    for route in routes:
        response = client.get(route)
        assert_private_response_denied(response)


@pytest.mark.django_db
def test_client_login_by_email_returns_only_active_scope():
    user_model = get_user_model()
    user = user_model.objects.create_user(email="client@example.com", password="pass")
    active_customer = Customer.objects.create(name="Active Customer")
    inactive_membership_customer = Customer.objects.create(name="Inactive Membership Customer")
    inactive_customer = Customer.objects.create(name="Inactive Customer", is_active=False)

    CustomerMembership.objects.create(
        customer=active_customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerMembership.objects.create(
        customer=inactive_membership_customer,
        user=user,
        role=CustomerMembership.Role.MEMBER,
        is_active=False,
    )
    CustomerMembership.objects.create(
        customer=inactive_customer,
        user=user,
        role=CustomerMembership.Role.MEMBER,
    )

    client = APIClient()

    assert client.login(email=user.email, password="pass") is True

    response = client.get(reverse("accounts:client-me"))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()

    assert payload["user"]["email"] == user.email
    assert payload["scope"]["customer_public_ids"] == [str(active_customer.public_id)]
    assert payload["memberships"] == [
        {
            "membership_public_id": str(
                user.customer_memberships.get(customer=active_customer).public_id
            ),
            "customer_public_id": str(active_customer.public_id),
            "customer_name": active_customer.name,
            "role": CustomerMembership.Role.OWNER,
            "is_owner": True,
        }
    ]


@pytest.mark.django_db
def test_client_cannot_access_customer_outside_scope():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    own_customer = Customer.objects.create(name="Own Customer")
    other_customer = Customer.objects.create(name="Other Customer")
    CustomerMembership.objects.create(customer=own_customer, user=user)

    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.get(
        reverse(
            "accounts:client-customer-detail",
            kwargs={"customer_public_id": other_customer.public_id},
        )
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_owner_only_endpoint_allows_owner_and_refuses_member():
    user_model = get_user_model()
    owner = user_model.objects.create_user(email="owner@example.com", password="pass")
    member = user_model.objects.create_user(email="member@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
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
    route = reverse(
        "accounts:client-customer-owner-zone", kwargs={"customer_public_id": customer.public_id}
    )

    owner_client = APIClient()
    member_client = APIClient()
    owner_client.login(email=owner.email, password="pass")
    member_client.login(email=member.email, password="pass")

    owner_response = owner_client.get(route)
    member_response = member_client.get(route)

    assert owner_response.status_code == status.HTTP_200_OK
    assert owner_response.json()["allowed_action"] == "manage_customer_memberships"
    assert member_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_inactive_membership_is_refused_from_customer_route():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    CustomerMembership.objects.create(customer=customer, user=user, is_active=False)

    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.get(
        reverse(
            "accounts:client-customer-detail", kwargs={"customer_public_id": customer.public_id}
        )
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_inactive_customer_is_refused_from_customer_route():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Acme", is_active=False)
    CustomerMembership.objects.create(customer=customer, user=user)

    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.get(
        reverse(
            "accounts:client-customer-detail", kwargs={"customer_public_id": customer.public_id}
        )
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_route_is_refused_to_client_user():
    user = get_user_model().objects.create_user(email="client@example.com", password="pass")
    client = APIClient()
    client.login(email=user.email, password="pass")

    response = client.get(reverse("accounts:staff-me"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_route_is_refused_to_staff_without_permission():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    client = APIClient()
    client.login(email=staff_user.email, password="pass")

    response = client.get(reverse("accounts:staff-me"))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_route_is_allowed_to_authorized_staff():
    user_model = get_user_model()
    staff_user = user_model.objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
        staff_mfa_required=True,
        staff_mfa_enabled=False,
    )
    permission = Permission.objects.get(codename="access_staff_portal")
    staff_user.user_permissions.add(permission)
    client = APIClient()

    assert client.login(email=staff_user.email, password="pass") is True

    response = client.get(reverse("accounts:staff-me"))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["user"]["email"] == staff_user.email
    assert payload["staff"] == {
        "has_staff_portal_access": True,
        "staff_mfa_required": True,
        "staff_mfa_enabled": False,
    }


@pytest.mark.django_db
def test_hybrid_client_staff_user_keeps_separate_client_and_staff_scope():
    user_model = get_user_model()
    hybrid_user = user_model.objects.create_user(
        email="hybrid@example.com",
        password="pass",
        is_staff=True,
        staff_mfa_required=True,
        staff_mfa_enabled=True,
    )
    permission = Permission.objects.get(codename="access_staff_portal")
    hybrid_user.user_permissions.add(permission)

    customer = Customer.objects.create(name="Hybrid Customer")
    CustomerMembership.objects.create(
        customer=customer,
        user=hybrid_user,
        role=CustomerMembership.Role.OWNER,
    )

    client = APIClient()
    assert client.login(email=hybrid_user.email, password="pass") is True

    client_scope_response = client.get(reverse("accounts:client-me"))
    staff_scope_response = client.get(reverse("accounts:staff-me"))
    customer_response = client.get(
        reverse(
            "accounts:client-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
    )

    assert client_scope_response.status_code == status.HTTP_200_OK
    assert client_scope_response.json()["scope"]["customer_public_ids"] == [str(customer.public_id)]
    assert client_scope_response.json()["memberships"] == [
        {
            "membership_public_id": str(hybrid_user.customer_memberships.get().public_id),
            "customer_public_id": str(customer.public_id),
            "customer_name": customer.name,
            "role": CustomerMembership.Role.OWNER,
            "is_owner": True,
        }
    ]

    assert staff_scope_response.status_code == status.HTTP_200_OK
    assert staff_scope_response.json()["staff"] == {
        "has_staff_portal_access": True,
        "staff_mfa_required": True,
        "staff_mfa_enabled": True,
    }
    assert customer_response.status_code == status.HTTP_200_OK
