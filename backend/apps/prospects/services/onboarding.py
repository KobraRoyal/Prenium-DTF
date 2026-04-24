from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.auditlog.services import record_event
from apps.customers.models import Customer, CustomerMembership

from ..models import ProspectProfile

User = get_user_model()


@dataclass(frozen=True)
class ProspectDraft:
    step1: dict[str, Any]
    step2: dict[str, Any]
    step3: dict[str, Any]


class ProspectOnboardingError(Exception):
    """Erreur métier création prospect (ex. email déjà utilisé)."""


class ProspectOnboardingService:
    """Création User + Customer + membership + ProspectProfile à partir du brouillon session."""

    @transaction.atomic
    def complete_from_draft(
        self,
        *,
        draft: ProspectDraft,
        password: str,
        ip_address: str | None = None,
    ) -> ProspectProfile:
        email = (draft.step1.get("email") or "").strip().lower()
        if not email:
            raise ProspectOnboardingError("Email manquant.")

        if User.objects.filter(email__iexact=email).exists():
            raise ProspectOnboardingError("Un compte existe déjà avec cet email.")

        first_name = draft.step1.get("first_name", "").strip()
        last_name = draft.step1.get("last_name", "").strip()
        company = draft.step1.get("company", "").strip()

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        customer = Customer.objects.create(
            name=company or f"{first_name} {last_name}".strip() or email,
            billing_email=email,
        )

        CustomerMembership.objects.create(
            customer=customer,
            user=user,
            role=CustomerMembership.Role.OWNER,
        )

        profile = ProspectProfile.objects.create(
            user=user,
            customer=customer,
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=(draft.step1.get("phone") or "").strip(),
            company=company,
            country=draft.step1.get("country") or "",
            activity_type=draft.step1.get("activity_type") or "",
            service_interest=draft.step2.get("service_interest") or "",
            main_goal=(draft.step2.get("main_goal") or "").strip(),
            project_timing=draft.step2.get("project_timing") or "",
            monthly_volume=draft.step3.get("monthly_volume") or "",
            order_frequency=draft.step3.get("order_frequency") or "",
            urgency=draft.step3.get("urgency") or "",
            status=ProspectProfile.Status.ACCOUNT_CREATED,
            source="tunnel_web",
        )

        record_event(
            action="prospect.account_created",
            actor=user,
            target=profile,
            ip_address=ip_address,
            metadata={"customer_public_id": str(customer.public_id)},
        )

        return profile
