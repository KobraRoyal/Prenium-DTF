from unittest.mock import patch

import pytest
from apps.customers.models import Customer, CustomerInvitation, CustomerMembership
from apps.customers.services.invitations import make_invitation_token
from apps.prospects.models import ProspectProfile
from apps.prospects.services.onboarding import (
    ProspectReviewService,
    make_email_verification_token,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_prospect_rate_limit_cache():
    cache.clear()


def step1_payload(**overrides):
    payload = {
        "first_name": "Jean",
        "last_name": "Martin",
        "email": "prospect@example.com",
        "phone": "+33612345678",
        "company": "Atelier Martin",
        "country": "FR",
        "siren": "123 456 789",
        "vat_number": "",
        "activity_type": "brand",
    }
    payload.update(overrides)
    return payload


def step2_payload(**overrides):
    payload = {
        "service_interest": "dtf_meter",
        "main_goal": "Lancer une capsule",
        "project_timing": "immediate",
        "monthly_volume": "10_50",
        "order_frequency": "monthly",
        "urgency": "medium",
    }
    payload.update(overrides)
    return payload


def submit_request(client: Client, *, email="prospect@example.com") -> ProspectProfile:
    assert client.post(reverse("prospects:step1"), step1_payload(email=email)).status_code == 302
    assert client.post(reverse("prospects:step2"), step2_payload()).status_code == 302
    with patch(
        "apps.notifications.tasks.send_access_request_verification_email_task.delay"
    ) as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(reverse("prospects:step3"), {"terms_accepted": "on"})
    assert response.status_code == 302
    profile = ProspectProfile.objects.get(normalized_email=email)
    delay.assert_called_once_with(str(profile.public_id))
    return profile


@pytest.mark.django_db
def test_france_requires_nine_digit_siren_and_foreign_country_requires_tax_id(client):
    response = client.post(reverse("prospects:step1"), step1_payload(siren="123"))
    assert response.status_code == 200
    assert "9 chiffres" in response.content.decode()

    response = client.post(
        reverse("prospects:step1"),
        step1_payload(country="BE", siren="", vat_number=""),
    )
    assert response.status_code == 200
    assert "identifiant fiscal valide" in response.content.decode()

    response = client.post(
        reverse("prospects:step1"),
        step1_payload(country="BE", siren="", vat_number="BE 0123.456.789"),
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_submission_creates_only_pending_request_not_user_or_customer(client):
    profile = submit_request(client)

    assert profile.status == ProspectProfile.Status.PENDING_EMAIL_VERIFICATION
    assert profile.siren == "123456789"
    assert profile.is_open is True
    assert profile.user is None
    assert profile.customer is None
    assert not User.objects.filter(email=profile.email).exists()
    assert Customer.objects.count() == 0


@pytest.mark.django_db
def test_resubmission_rotates_verification_token_and_resends_email(client):
    profile = submit_request(client)
    initial_version = profile.verification_version

    assert client.post(reverse("prospects:step1"), step1_payload()).status_code == 302
    assert client.post(reverse("prospects:step2"), step2_payload()).status_code == 302
    with patch(
        "apps.notifications.tasks.send_access_request_verification_email_task.delay"
    ) as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(reverse("prospects:step3"), {"terms_accepted": "on"})

    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.verification_version == initial_version + 1
    delay.assert_called_once_with(str(profile.public_id))


@pytest.mark.django_db
@override_settings(PROSPECT_RATE_LIMIT_MAX_ATTEMPTS=2)
def test_spoofed_forwarded_ip_does_not_bypass_prospect_rate_limit(client):
    for forwarded_ip in ("198.51.100.1", "198.51.100.2"):
        assert client.post(reverse("prospects:step1"), step1_payload()).status_code == 302
        assert client.post(reverse("prospects:step2"), step2_payload()).status_code == 302
        with patch("apps.notifications.tasks.send_access_request_verification_email_task.delay"):
            with TestCase.captureOnCommitCallbacks(execute=True):
                response = client.post(
                    reverse("prospects:step3"),
                    {"terms_accepted": "on"},
                    HTTP_X_FORWARDED_FOR=forwarded_ip,
                )
        assert response.status_code == 302

    assert client.post(reverse("prospects:step1"), step1_payload()).status_code == 302
    assert client.post(reverse("prospects:step2"), step2_payload()).status_code == 302
    response = client.post(
        reverse("prospects:step3"),
        {"terms_accepted": "on"},
        HTTP_X_FORWARDED_FOR="198.51.100.3",
    )
    assert response.status_code == 429


@pytest.mark.django_db
def test_email_verification_moves_request_to_staff_queue_and_is_idempotent(client):
    profile = submit_request(client)
    token = make_email_verification_token(profile)
    url = reverse("prospects:verify-email", kwargs={"token": token})

    with patch(
        "apps.notifications.tasks.send_access_request_submitted_internal_email_task.delay"
    ) as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.get(url)
    assert response.status_code == 200
    profile.refresh_from_db()
    assert profile.status == ProspectProfile.Status.PENDING_REVIEW
    assert profile.email_verified_at is not None
    delay.assert_called_once_with(str(profile.public_id))

    with patch(
        "apps.notifications.tasks.send_access_request_submitted_internal_email_task.delay"
    ) as repeated_delay:
        assert client.get(url).status_code == 200
    repeated_delay.assert_not_called()


@pytest.mark.django_db
def test_only_reviewer_can_approve_and_approval_keeps_org_inactive(client):
    profile = submit_request(client)
    profile.status = ProspectProfile.Status.PENDING_REVIEW
    profile.save(update_fields=("status", "updated_at"))
    basic_staff = User.objects.create_user(
        email="staff@example.com", password="pass", is_staff=True
    )
    basic_staff.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client.force_login(basic_staff)
    approve_url = reverse(
        "portal:staff-access-request-approve",
        kwargs={"profile_public_id": profile.public_id},
    )
    assert client.post(approve_url).status_code == 403

    reviewer = User.objects.create_user(
        email="reviewer@example.com", password="pass", is_staff=True
    )
    reviewer.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_prospectprofile"),
        Permission.objects.get(codename="review_prospectprofile"),
    )
    client.force_login(reviewer)
    with patch("apps.notifications.tasks.send_access_request_approved_email_task.delay") as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(approve_url, {"review_note": "SIREN contrôlé"})
    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.status == ProspectProfile.Status.APPROVED_PENDING_ACTIVATION
    assert profile.customer is not None
    assert profile.customer.is_active is False
    invitation = CustomerInvitation.objects.get(customer=profile.customer)
    assert invitation.role == CustomerMembership.Role.OWNER
    delay.assert_called_once_with(str(invitation.public_id))


@pytest.mark.django_db
def test_owner_activation_creates_account_and_membership_without_auto_login(client):
    profile = submit_request(client)
    profile.status = ProspectProfile.Status.PENDING_REVIEW
    profile.save(update_fields=("status", "updated_at"))
    reviewer = User.objects.create_user(
        email="reviewer@example.com",
        password="pass",
        is_staff=True,
    )
    reviewer.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="review_prospectprofile"),
    )
    with patch("apps.notifications.tasks.send_access_request_approved_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            profile = ProspectReviewService().approve(
                profile_public_id=profile.public_id,
                actor=reviewer,
            )
    invitation = CustomerInvitation.objects.get(customer=profile.customer)
    token = make_invitation_token(invitation)

    with patch("apps.notifications.tasks.send_account_activated_email_task.delay"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("portal:customer-invitation-accept", kwargs={"token": token}),
                {
                    "password": "ComplexPass-2026!",
                    "password_confirm": "ComplexPass-2026!",
                },
            )
    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.status == ProspectProfile.Status.ACTIVE
    assert profile.customer.is_active is True
    assert profile.user is not None
    membership = CustomerMembership.objects.get(customer=profile.customer, user=profile.user)
    assert membership.role == CustomerMembership.Role.OWNER
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_simplified_tunnel_has_three_steps_and_legacy_step4_redirects(client):
    assert reverse("prospects:step1") == "/demande-acces/etape-1/"
    response = client.get(reverse("prospects:step4"))
    assert response.status_code == 302
    assert response.url == reverse("prospects:step3")
