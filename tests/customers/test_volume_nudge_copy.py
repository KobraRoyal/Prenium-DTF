from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import (
    Customer,
    CustomerMembership,
    CustomerVolumeDiscountTier,
    VolumeDiscountDashboardCopy,
)
from apps.customers.services.volume_nudge_copy import (
    COPY_FIELDS,
    DEFAULT_NUDGE_COPY,
    interpolate_nudge_copy,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient


def _staff_user(*, email: str, pricing_permission: bool):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    user.user_permissions.add(Permission.objects.get(codename="view_customer"))
    if pricing_permission:
        user.user_permissions.add(Permission.objects.get(codename="manage_customer_pricing"))
    return user


def _copy_payload(**overrides):
    payload = {field: "" for field in COPY_FIELDS}
    payload.update(overrides)
    return payload


def test_default_copy_fits_field_limit():
    for field, text in DEFAULT_NUDGE_COPY.items():
        assert len(text) <= 400, field


def test_interpolate_keeps_unknown_placeholders():
    assert interpolate_nudge_copy("Reste {remaining_m} {foo}", {"remaining_m": "3,2"}) == (
        "Reste 3,2 {foo}"
    )


@pytest.mark.django_db
def test_staff_updates_dashboard_copy_with_pricing_permission_only():
    viewer = _staff_user(email="copy-viewer@example.com", pricing_permission=False)
    manager = _staff_user(email="copy-manager@example.com", pricing_permission=True)
    settings_url = reverse("portal:staff-default-volume-discount-settings")
    copy_url = reverse("portal:staff-volume-discount-dashboard-copy")
    client = APIClient()

    assert client.login(email=viewer.email, password="pass") is True
    assert client.get(settings_url).status_code == 403
    assert client.post(copy_url, _copy_payload()).status_code == 403

    client.logout()
    assert client.login(email=manager.email, password="pass") is True
    html = client.get(settings_url).content.decode()
    assert 'data-testid="volume-nudge-copy"' in html
    assert "Messages dashboard client" in html
    assert "{remaining_m}" in html

    response = client.post(
        copy_url,
        _copy_payload(
            audience="immediate",
            start_immediate="Go : encore {remaining_m} m pour -{next_percent} %.",
        ),
    )
    assert response.status_code == 302
    row = VolumeDiscountDashboardCopy.objects.get()
    assert row.start_immediate == "Go : encore {remaining_m} m pour -{next_percent} %."
    assert AuditLogEntry.objects.filter(
        action="customer.volume_discount_dashboard_copy_updated",
        target_public_id=row.public_id,
    ).exists()


@pytest.mark.django_db
def test_staff_copy_is_used_on_client_dashboard_and_escaped():
    manager = _staff_user(email="copy-escape@example.com", pricing_permission=True)
    user = get_user_model().objects.create_user(
        email="copy-client@example.com",
        password="pass",
    )
    customer = Customer.objects.create(
        name="Atelier copy",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("5.0000"),
        discount_percent=Decimal("10.00"),
    )
    staff_client = APIClient()
    assert staff_client.login(email=manager.email, password="pass") is True
    staff_client.post(
        reverse("portal:staff-volume-discount-dashboard-copy"),
        _copy_payload(start_immediate="<b>Promo</b> {remaining_m} m et c’est plié."),
    )

    portal = APIClient()
    assert portal.login(email=user.email, password="pass") is True
    html = portal.get(reverse("portal:client-dashboard")).content.decode()
    assert "&lt;b&gt;Promo&lt;/b&gt; 5 m et c’est plié." in html
    assert "<b>Promo</b>" not in html


@pytest.mark.django_db
def test_staff_restores_default_dashboard_copy():
    manager = _staff_user(email="copy-restore@example.com", pricing_permission=True)
    client = APIClient()
    assert client.login(email=manager.email, password="pass") is True
    copy_url = reverse("portal:staff-volume-discount-dashboard-copy")
    client.post(copy_url, _copy_payload(start_immediate="Texte custom."))
    response = client.post(
        copy_url,
        {**_copy_payload(start_immediate="Texte custom."), "restore_defaults": "1"},
    )
    assert response.status_code == 302
    row = VolumeDiscountDashboardCopy.objects.get()
    assert row.start_immediate == ""
