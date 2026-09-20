"""Régression : flash hors-sujet ne polluent plus les pages Équipe (client + atelier)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import StaffMembership
from apps.accounts.services.staff_roles import sync_staff_access
from apps.customers.models import Customer, CustomerMembership
from apps.portal.views_access_management import ClientTeamView
from apps.portal.views_payments import user_facing_payment_error
from apps.portal.views_staff_team import StaffTeamView

User = get_user_model()
TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"


def _flash_payload(html: str) -> list[dict] | None:
    match = re.search(
        r'<script id="prenium-django-flash" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    if match is None:
        return None
    return json.loads(match.group(1))


class ClientTeamFlashMessagesTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(email="owner-flash@example.com", password="pass")
        self.customer = Customer.objects.create(
            name="Org flash",
            billing_email="owner-flash@example.com",
        )
        CustomerMembership.objects.create(
            customer=self.customer,
            user=self.owner,
            role=CustomerMembership.Role.OWNER,
        )
        self.team_url = reverse(
            "portal:client-team",
            kwargs={"customer_public_id": self.customer.public_id},
        )

    def test_stale_payment_messages_are_silently_cleared_on_team_page(self) -> None:
        factory = RequestFactory()
        request = factory.get(self.team_url)
        request.user = self.owner
        request.session = self.client.session
        setattr(request, "_messages", FallbackStorage(request))
        for text in (
            "RESOURCE_NOT_FOUND INVALID_RESOURCE_ID",
            "Paiement non validé. Vous pouvez relancer un nouveau règlement.",
            "Le prestataire de paiement est temporairement indisponible.",
        ):
            messages.error(request, text)

        response = ClientTeamView.as_view()(
            request,
            customer_public_id=self.customer.public_id,
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        self.assertNotIn('class="alert alert--danger"', html)
        self.assertNotIn("RESOURCE_NOT_FOUND", html)
        self.assertNotIn("prestataire de paiement", html)
        self.assertIsNone(_flash_payload(html))

    def test_team_tagged_feedback_still_shows_as_toast(self) -> None:
        factory = RequestFactory()
        request = factory.get(self.team_url)
        request.user = self.owner
        request.session = self.client.session
        setattr(request, "_messages", FallbackStorage(request))
        messages.success(request, "Rôle mis à jour.", extra_tags="team")
        messages.error(request, "RESOURCE_NOT_FOUND INVALID_RESOURCE_ID")

        response = ClientTeamView.as_view()(
            request,
            customer_public_id=self.customer.public_id,
        )
        html = response.content.decode()
        payload = _flash_payload(html)
        self.assertIsNotNone(payload)
        self.assertEqual(
            [(row["variant"], row["message"]) for row in payload],
            [("success", "Rôle mis à jour.")],
        )
        self.assertNotIn("RESOURCE_NOT_FOUND", html)

    def test_team_templates_no_longer_dump_django_messages_as_alerts(self) -> None:
        for relative in ("portal/client/team.html", "portal/staff/team.html"):
            source = (TEMPLATES_DIR / relative).read_text(encoding="utf-8")
            self.assertNotIn("for message in messages", source, msg=relative)
        layout = (TEMPLATES_DIR / "portal" / "layout.html").read_text(encoding="utf-8")
        self.assertIn("django_messages_toasts", layout)


class StaffTeamFlashMessagesTests(TestCase):
    def setUp(self) -> None:
        self.owner = User.objects.create_user(email="staff-flash@example.com", password="pass")
        self.owner.is_superuser = True
        self.owner.is_staff = True
        self.owner.save(update_fields=("is_superuser", "is_staff", "updated_at"))
        permission = Permission.objects.get(
            codename="access_staff_portal",
            content_type__app_label="accounts",
        )
        self.owner.user_permissions.add(permission)
        StaffMembership.objects.create(
            user=self.owner,
            role=StaffMembership.Role.OWNER,
            is_active=True,
        )
        sync_staff_access(
            user=self.owner,
            role=StaffMembership.Role.OWNER,
            is_active=True,
        )
        self.team_url = reverse("portal:staff-team")

    def test_stale_account_and_payment_messages_are_silently_cleared(self) -> None:
        factory = RequestFactory()
        request = factory.get(self.team_url)
        request.user = self.owner
        request.session = self.client.session
        setattr(request, "_messages", FallbackStorage(request))
        for text in (
            "Compte client mis à jour.",
            "RESOURCE_NOT_FOUND INVALID_RESOURCE_ID",
            "Compte client mis à jour.",
        ):
            level = messages.ERROR if "RESOURCE" in text else messages.SUCCESS
            messages.add_message(request, level, text)

        response = StaffTeamView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()

        self.assertNotIn('class="alert alert--success"', html)
        self.assertNotIn('class="alert alert--danger"', html)
        self.assertNotIn("RESOURCE_NOT_FOUND", html)
        self.assertNotIn("Compte client mis à jour.", html)
        self.assertIsNone(_flash_payload(html))


class PaymentErrorCopyTests(TestCase):
    def test_provider_resource_errors_are_sanitized(self) -> None:
        raw = ValidationError("RESOURCE_NOT_FOUND INVALID_RESOURCE_ID")
        self.assertEqual(
            user_facing_payment_error(raw),
            "Paiement non validé. Vous pouvez relancer un nouveau règlement.",
        )

    def test_business_validation_errors_pass_through(self) -> None:
        raw = ValidationError(
            "Un paiement est déjà ouvert. Terminez-le avant de changer de moyen de paiement."
        )
        self.assertEqual(user_facing_payment_error(raw), raw.messages[0])
