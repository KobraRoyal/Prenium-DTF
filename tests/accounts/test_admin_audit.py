from decimal import Decimal
from types import SimpleNamespace

import pytest
from apps.accounts.admin import UserAdmin
from apps.auditlog.models import AuditLogEntry
from apps.customers.admin import CustomerAdmin, CustomerMembershipAdmin
from apps.customers.models import Customer, CustomerMembership
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory


def build_admin_request(user, path: str):
    request = RequestFactory().post(path)
    request.user = user
    return request


def build_admin_form(instance):
    return SimpleNamespace(instance=instance, save_m2m=lambda: None)


@pytest.mark.django_db
def test_user_admin_sensitive_update_writes_audit_entry():
    user_model = get_user_model()
    actor = user_model.objects.create_superuser(email="admin@example.com", password="pass")
    target = user_model.objects.create_user(email="staff@example.com", password="pass")
    user_admin = UserAdmin(user_model, admin.site)
    request = build_admin_request(actor, "/admin/accounts/user/1/change/")

    target.is_staff = True
    form = build_admin_form(target)

    user_admin.save_model(request, target, form, change=True)
    user_admin.save_related(request, form, [], change=True)

    entry = AuditLogEntry.objects.get(action="admin.user.updated")

    assert entry.actor == actor
    assert entry.target_public_id == target.public_id
    assert entry.metadata["changes"]["is_staff"] == {"before": False, "after": True}
    assert entry.metadata["source"] == "django_admin"


@pytest.mark.django_db
def test_customer_membership_admin_role_change_writes_audit_entry():
    user_model = get_user_model()
    actor = user_model.objects.create_superuser(email="admin@example.com", password="pass")
    customer_user = user_model.objects.create_user(email="client@example.com", password="pass")
    customer = Customer.objects.create(name="Acme")
    membership = CustomerMembership.objects.create(
        customer=customer,
        user=customer_user,
        role=CustomerMembership.Role.MEMBER,
    )
    membership_admin = CustomerMembershipAdmin(CustomerMembership, admin.site)
    request = build_admin_request(actor, "/admin/customers/customermembership/1/change/")

    membership.role = CustomerMembership.Role.OWNER
    form = build_admin_form(membership)

    membership_admin.save_model(request, membership, form, change=True)
    membership_admin.save_related(request, form, [], change=True)

    entry = AuditLogEntry.objects.get(action="admin.customer_membership.updated")

    assert entry.actor == actor
    assert entry.target_public_id == membership.public_id
    assert entry.metadata["changes"]["role"] == {
        "before": CustomerMembership.Role.MEMBER,
        "after": CustomerMembership.Role.OWNER,
    }


@pytest.mark.django_db
def test_customer_admin_decimal_fee_change_writes_json_safe_audit_metadata():
    """Les Decimal dans l’audit admin sont sérialisés (metadata JSON)."""
    user_model = get_user_model()
    actor = user_model.objects.create_superuser(email="admin-dec@example.com", password="pass")
    customer = Customer.objects.create(name="DecimalCo", negotiated_file_preparation_fee_eur=None)
    customer_admin = CustomerAdmin(Customer, admin.site)
    request = build_admin_request(actor, "/admin/customers/customer/1/change/")

    customer.negotiated_file_preparation_fee_eur = Decimal("12.50")
    form = build_admin_form(customer)

    customer_admin.save_model(request, customer, form, change=True)
    customer_admin.save_related(request, form, [], change=True)

    entry = AuditLogEntry.objects.get(action="admin.customer.updated")
    assert entry.metadata["changes"]["negotiated_file_preparation_fee_eur"] == {
        "before": None,
        "after": "12.50",
    }
