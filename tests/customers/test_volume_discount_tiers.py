from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import (
    Customer,
    CustomerVolumeDiscountTier,
    DefaultCustomerVolumeDiscountTier,
)
from apps.prospects.models import ProspectProfile
from apps.prospects.services.onboarding import ProspectReviewService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient


def _staff_user(*, email: str, pricing_permission: bool):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    user.user_permissions.add(Permission.objects.get(codename="view_customer"))
    if pricing_permission:
        user.user_permissions.add(Permission.objects.get(codename="manage_customer_pricing"))
    return user


def _new_tier_payload(*, threshold="10.0000", discount="5.00", active=True):
    payload = {
        "new-minimum_monthly_linear_m": threshold,
        "new-discount_percent": discount,
    }
    if active:
        payload["new-is_active"] = "on"
    return payload


@pytest.mark.django_db
def test_staff_can_create_customer_tier_with_audit_and_see_it_in_atelier():
    staff = _staff_user(email="pricing@example.com", pricing_permission=True)
    customer = Customer.objects.create(name="Client encours", default_billing_mode="deferred")
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True

    response = client.post(
        reverse(
            "portal:staff-customer-volume-discount-tier-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        _new_tier_payload(threshold="25.0000", discount="7.50"),
    )
    assert response.status_code == 302
    tier = CustomerVolumeDiscountTier.objects.get(customer=customer)
    assert tier.minimum_monthly_linear_m == Decimal("25.0000")
    assert tier.discount_percent == Decimal("7.50")
    assert AuditLogEntry.objects.filter(
        action="customer.volume_discount_tier_created",
        target_public_id=customer.public_id,
    ).exists()

    detail = client.get(
        reverse(
            "portal:staff-customer-detail",
            kwargs={"customer_public_id": customer.public_id},
        )
    )
    assert detail.status_code == 200
    assert "Remise volume mensuelle" in detail.content.decode()
    assert 'value="25.0000"' in detail.content.decode()
    assert 'data-testid="monthly-volume-discount-summary"' in detail.content.decode()
    assert "volume-discount-overview" in detail.content.decode()
    assert "Prochain objectif" in detail.content.decode()
    assert "volume-tier-item--next" in detail.content.decode()
    assert "Voir la grille par défaut" in detail.content.decode()


@pytest.mark.django_db
def test_tier_configuration_requires_permission_and_deferred_customer():
    viewer = _staff_user(email="viewer-volume@example.com", pricing_permission=False)
    immediate_customer = Customer.objects.create(
        name="Comptant",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    client = APIClient()
    assert client.login(email=viewer.email, password="pass") is True
    url = reverse(
        "portal:staff-customer-volume-discount-tier-create",
        kwargs={"customer_public_id": immediate_customer.public_id},
    )
    assert client.post(url, _new_tier_payload()).status_code == 403

    staff = _staff_user(email="manager-volume@example.com", pricing_permission=True)
    client.logout()
    assert client.login(email=staff.email, password="pass") is True
    response = client.post(url, _new_tier_payload())
    assert response.status_code == 200
    assert "réservés aux clients avec encours" in response.content.decode()
    assert not CustomerVolumeDiscountTier.objects.filter(customer=immediate_customer).exists()


@pytest.mark.django_db
def test_tier_update_is_customer_scoped_and_ladder_must_be_strictly_degressive():
    staff = _staff_user(email="scope-volume@example.com", pricing_permission=True)
    customer = Customer.objects.create(name="A", default_billing_mode="deferred")
    other_customer = Customer.objects.create(name="B", default_billing_mode="deferred")
    low = CustomerVolumeDiscountTier.objects.create(
        customer=customer,
        minimum_monthly_linear_m=Decimal("10.0000"),
        discount_percent=Decimal("5.00"),
    )
    foreign_tier = CustomerVolumeDiscountTier.objects.create(
        customer=other_customer,
        minimum_monthly_linear_m=Decimal("20.0000"),
        discount_percent=Decimal("10.00"),
    )
    client = APIClient()
    assert client.login(email=staff.email, password="pass") is True
    cross_customer_url = reverse(
        "portal:staff-customer-volume-discount-tier-update",
        kwargs={
            "customer_public_id": customer.public_id,
            "tier_public_id": foreign_tier.public_id,
        },
    )
    assert client.post(cross_customer_url, {}).status_code == 404

    create_url = reverse(
        "portal:staff-customer-volume-discount-tier-create",
        kwargs={"customer_public_id": customer.public_id},
    )
    invalid = client.post(
        create_url,
        _new_tier_payload(threshold="20.0000", discount="4.00"),
    )
    assert invalid.status_code == 200
    assert "doit augmenter strictement" in invalid.content.decode()
    assert CustomerVolumeDiscountTier.objects.filter(customer=customer).count() == 1
    low.refresh_from_db()
    assert low.discount_percent == Decimal("5.00")


@pytest.mark.django_db
def test_staff_configures_default_ladder_with_pricing_permission_only():
    viewer = _staff_user(email="default-viewer@example.com", pricing_permission=False)
    manager = _staff_user(email="default-manager@example.com", pricing_permission=True)
    url = reverse("portal:staff-default-volume-discount-settings")
    create_url = reverse("portal:staff-default-volume-discount-tier-create")
    client = APIClient()

    assert client.login(email=viewer.email, password="pass") is True
    assert client.get(url).status_code == 403
    assert client.post(create_url, _new_tier_payload()).status_code == 403

    client.logout()
    assert client.login(email=manager.email, password="pass") is True
    assert client.get(url).status_code == 200
    response = client.post(
        create_url,
        _new_tier_payload(threshold="40.0000", discount="8.00"),
    )
    assert response.status_code == 302
    tier = DefaultCustomerVolumeDiscountTier.objects.get()
    assert tier.minimum_monthly_linear_m == Decimal("40.0000")
    assert tier.discount_percent == Decimal("8.00")
    assert AuditLogEntry.objects.filter(
        action="customer.default_volume_discount_tier_created",
        target_public_id=tier.public_id,
    ).exists()
    html = client.get(url).content.decode()
    assert 'data-testid="default-volume-discount-settings"' in html
    assert "volume-tier-list" in html
    assert "Copié à la création" in html
    assert "<strong>1</strong>" in html
    assert "palier actif" in html
    assert "Modifier l’e-mail de palier" not in html
    assert "Configurer l’e-mail client" not in html


@pytest.mark.django_db
def test_approval_copies_only_active_default_tiers_to_new_deferred_customer():
    reviewer = get_user_model().objects.create_user(
        email="reviewer-default-tier@example.com",
        password="pass",
        is_staff=True,
    )
    reviewer.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="review_prospectprofile"),
    )
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m=Decimal("25.0000"),
        discount_percent=Decimal("5.00"),
    )
    DefaultCustomerVolumeDiscountTier.objects.create(
        minimum_monthly_linear_m=Decimal("50.0000"),
        discount_percent=Decimal("10.00"),
        is_active=False,
    )
    profile = ProspectProfile.objects.create(
        first_name="Camille",
        last_name="Martin",
        email="camille-default@example.com",
        normalized_email="camille-default@example.com",
        phone="+33612345678",
        company="Atelier Default",
        country="FR",
        siren="123456789",
        activity_type=ProspectProfile.ActivityType.WORKSHOP,
        service_interest=ProspectProfile.ServiceInterest.DTF_METER,
        project_timing=ProspectProfile.ProjectTiming.ONGOING,
        monthly_volume=ProspectProfile.MonthlyVolume.M10_50,
        order_frequency=ProspectProfile.OrderFrequency.MONTHLY,
        urgency=ProspectProfile.Urgency.MEDIUM,
        status=ProspectProfile.Status.PENDING_REVIEW,
        is_open=True,
    )

    with patch("apps.notifications.tasks.send_access_request_approved_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            profile = ProspectReviewService().approve(
                profile_public_id=profile.public_id,
                actor=reviewer,
            )

    tiers = list(profile.customer.volume_discount_tiers.all())
    assert profile.customer.default_billing_mode == Customer.DefaultBillingMode.DEFERRED
    assert len(tiers) == 1
    assert tiers[0].minimum_monthly_linear_m == Decimal("25.0000")
    assert tiers[0].discount_percent == Decimal("5.00")
    assert AuditLogEntry.objects.filter(
        action="customer.default_volume_discount_tiers_applied",
        target_public_id=profile.customer.public_id,
    ).exists()
