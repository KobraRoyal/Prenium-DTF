import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerBillingProfile, CustomerMembership
from apps.customers.services.administration import CustomerAdministrationService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient


def _staff_user(*, email: str, perms: list[str]):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    return user


@pytest.mark.django_db
def test_staff_without_view_customer_cannot_list_accounts():
    staff = _staff_user(email="ops@example.com", perms=["access_staff_portal"])
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True
    response = client.get(reverse("portal:staff-customer-list"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_staff_can_list_and_open_customer_detail():
    staff = _staff_user(
        email="commercial@example.com",
        perms=["access_staff_portal", "view_customer"],
    )
    customer = Customer.objects.create(name="Atelier Print", billing_email="print@example.com")
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    list_response = client.get(reverse("portal:staff-customer-list"))
    assert list_response.status_code == 200
    assert b"Atelier Print" in list_response.content

    detail_response = client.get(
        reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert detail_response.status_code == 200
    assert b"Conditions tarifaires" in detail_response.content
    assert b"staff-customer-focus" in detail_response.content
    assert b"Encours" in detail_response.content
    assert b'name="default_billing_mode"' not in detail_response.content


@pytest.mark.django_db
def test_staff_without_pricing_perm_cannot_post_pricing():
    staff = _staff_user(
        email="viewer@example.com",
        perms=["access_staff_portal", "view_customer"],
    )
    customer = Customer.objects.create(name="Sans Droit Tarif")
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    response = client.post(
        reverse(
            "portal:staff-customer-pricing-update",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {
            "billing_cycle": "monthly",
            "price_per_sqm_eur": "18.50",
            "enforce_credit_block": "on",
        },
    )
    assert response.status_code == 403
    assert not CustomerBillingProfile.objects.filter(customer=customer).exists()


@pytest.mark.django_db
def test_staff_can_update_pricing_conditions_with_audit():
    staff = _staff_user(
        email="tarif@example.com",
        perms=[
            "access_staff_portal",
            "view_customer",
            "manage_customer_pricing",
        ],
    )
    customer = Customer.objects.create(name="Client Tarif")
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    response = client.post(
        reverse(
            "portal:staff-customer-pricing-update",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {
            "billing_cycle": "bi_monthly",
            "price_per_sqm_eur": "19.90",
            "negotiated_file_preparation_fee_eur": "8.00",
            "credit_limit_eur": "1500.00",
            "enforce_credit_block": "on",
        },
    )
    assert response.status_code == 302
    customer.refresh_from_db()
    profile = customer.billing_profile
    assert str(customer.negotiated_file_preparation_fee_eur) == "8.00"
    assert str(profile.price_per_sqm_eur) == "19.90"
    assert profile.billing_cycle == CustomerBillingProfile.BillingCycle.BI_MONTHLY
    assert profile.enforce_credit_block is True
    assert AuditLogEntry.objects.filter(
        action="customer.pricing_conditions_updated",
        target_public_id=customer.public_id,
    ).exists()


@pytest.mark.django_db
def test_staff_can_update_account_and_memberships_are_visible():
    staff = _staff_user(
        email="account@example.com",
        perms=["access_staff_portal", "view_customer", "change_customer"],
    )
    customer = Customer.objects.create(name="Ancien Nom", billing_email="old@example.com")
    member = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=customer,
        user=member,
        role=CustomerMembership.Role.OWNER,
    )
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    detail = client.get(
        reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert detail.status_code == 200
    assert b"owner@example.com" in detail.content
    assert b'name="default_billing_mode"' in detail.content
    assert b"Comptant" in detail.content
    assert b"Encours" in detail.content

    response = client.post(
        reverse(
            "portal:staff-customer-account-update",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {
            "name": "Nouveau Nom",
            "billing_email": "new@example.com",
            "siren": "",
            "vat_number": "",
            "is_active": "on",
            "default_billing_mode": Customer.DefaultBillingMode.IMMEDIATE,
            "preferred_settlement_method": Customer.PreferredSettlementMethod.PAYPAL,
            "default_shipping_mode": Customer.DefaultShippingMode.CARRIER,
            "billing_address_line1": "",
            "billing_address_line2": "",
            "billing_postal_code": "",
            "billing_city": "",
            "billing_country": "FR",
            "shipping_address_line1": "",
            "shipping_address_line2": "",
            "shipping_postal_code": "",
            "shipping_city": "",
            "shipping_country": "FR",
            "notes": "Compte VIP",
        },
    )
    assert response.status_code == 302
    customer.refresh_from_db()
    assert customer.name == "Nouveau Nom"
    assert customer.billing_email == "new@example.com"
    assert customer.default_billing_mode == Customer.DefaultBillingMode.IMMEDIATE
    assert customer.preferred_settlement_method == Customer.PreferredSettlementMethod.PAYPAL
    assert AuditLogEntry.objects.filter(action="customer.account_updated").exists()


@pytest.mark.django_db
def test_create_b2b_order_uses_customer_default_billing_mode():
    from apps.orders.models import Order
    from apps.orders.services.orders import OrderService

    user = get_user_model().objects.create_user(email="cb-default@example.com", password="pass")
    customer = Customer.objects.create(
        name="Default CB",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(customer=customer, user=user)
    order = OrderService().create_b2b_deferred_order(
        customer=customer,
        actor=user,
        source="client_portal",
    )
    assert order.billing_mode == Order.BillingMode.IMMEDIATE
    assert order.uses_atelier_pricing() is True


@pytest.mark.django_db
def test_administration_service_search_filters_customers():
    Customer.objects.create(name="Alpha DTF", billing_email="alpha@example.com")
    Customer.objects.create(name="Beta Print", billing_email="beta@example.com", is_active=False)
    service = CustomerAdministrationService()
    assert service.list_customers(search="alpha").count() == 1
    assert service.list_customers(active_only=False).count() == 1
    assert service.list_customers(active_only=None).count() == 2
