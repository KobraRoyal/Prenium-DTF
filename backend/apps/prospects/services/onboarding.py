from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core import signing
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.customers.models import Customer

from ..models import ProspectProfile

EMAIL_VERIFICATION_SALT = "prenium.prospect.email-verification.v1"
EMAIL_VERIFICATION_MAX_AGE_SECONDS = 48 * 60 * 60


@dataclass(frozen=True)
class ProspectDraft:
    step1: dict[str, Any]
    step2: dict[str, Any]


class ProspectOnboardingError(Exception):
    """Erreur métier du workflow de demande d'accès."""


def make_email_verification_token(profile: ProspectProfile) -> str:
    return signing.dumps(
        {"profile": str(profile.public_id), "version": profile.verification_version},
        salt=EMAIL_VERIFICATION_SALT,
        compress=True,
    )


def read_email_verification_token(token: str) -> dict[str, object]:
    try:
        payload = signing.loads(
            token,
            salt=EMAIL_VERIFICATION_SALT,
            max_age=EMAIL_VERIFICATION_MAX_AGE_SECONDS,
        )
    except signing.BadSignature as exc:
        raise ProspectOnboardingError("Ce lien de vérification est invalide ou expiré.") from exc
    if not isinstance(payload, dict):
        raise ProspectOnboardingError("Ce lien de vérification est invalide ou expiré.")
    return payload


class ProspectOnboardingService:
    """Soumission et vérification d'une demande sans créer de compte client."""

    @transaction.atomic
    def submit_from_draft(
        self,
        *,
        draft: ProspectDraft,
        ip_address: str | None = None,
    ) -> ProspectProfile:
        email = (draft.step1.get("email") or "").strip().lower()
        if not email:
            raise ProspectOnboardingError("E-mail professionnel manquant.")

        existing = (
            ProspectProfile.objects.select_for_update()
            .filter(normalized_email=email, is_open=True)
            .first()
        )
        if existing is not None:
            if existing.status == ProspectProfile.Status.PENDING_EMAIL_VERIFICATION:
                existing.verification_version += 1
                existing.save(update_fields=("verification_version", "updated_at"))
                from apps.notifications.services.transactional import (
                    schedule_access_request_verification_email,
                )

                schedule_access_request_verification_email(profile_public_id=existing.public_id)
            return existing

        first_name = str(draft.step1.get("first_name") or "").strip()
        last_name = str(draft.step1.get("last_name") or "").strip()
        company = str(draft.step1.get("company") or "").strip()
        profile = ProspectProfile.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            normalized_email=email,
            phone=str(draft.step1.get("phone") or "").strip(),
            company=company,
            country=str(draft.step1.get("country") or "").upper(),
            siren=str(draft.step1.get("siren") or ""),
            vat_number=str(draft.step1.get("vat_number") or "").upper(),
            activity_type=str(draft.step1.get("activity_type") or ""),
            service_interest=str(draft.step2.get("service_interest") or ""),
            main_goal=str(draft.step2.get("main_goal") or "").strip(),
            project_timing=str(draft.step2.get("project_timing") or ""),
            monthly_volume=str(draft.step2.get("monthly_volume") or ""),
            order_frequency=str(draft.step2.get("order_frequency") or ""),
            urgency=str(draft.step2.get("urgency") or ""),
            status=ProspectProfile.Status.PENDING_EMAIL_VERIFICATION,
            is_open=True,
            submitted_at=timezone.now(),
            terms_accepted_at=timezone.now(),
            source="tunnel_web",
        )
        record_event(
            action="prospect.access_request.submitted",
            target=profile,
            ip_address=ip_address,
            metadata={"country": profile.country, "source": profile.source},
        )

        from apps.notifications.services.transactional import (
            schedule_access_request_verification_email,
        )

        schedule_access_request_verification_email(profile_public_id=profile.public_id)
        return profile

    @transaction.atomic
    def verify_email(self, *, token: str, ip_address: str | None = None) -> ProspectProfile:
        payload = read_email_verification_token(token)
        profile = (
            ProspectProfile.objects.select_for_update()
            .filter(public_id=payload.get("profile"))
            .first()
        )
        if profile is None or profile.verification_version != payload.get("version"):
            raise ProspectOnboardingError("Ce lien de vérification est invalide ou expiré.")
        if profile.status == ProspectProfile.Status.PENDING_REVIEW:
            return profile
        if profile.status != ProspectProfile.Status.PENDING_EMAIL_VERIFICATION:
            raise ProspectOnboardingError("Cette demande ne peut plus être vérifiée.")

        profile.status = ProspectProfile.Status.PENDING_REVIEW
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=("status", "email_verified_at", "updated_at"))
        record_event(
            action="prospect.access_request.email_verified",
            target=profile,
            ip_address=ip_address,
        )

        from apps.notifications.services.transactional import (
            schedule_access_request_submitted_internal_email,
        )

        schedule_access_request_submitted_internal_email(profile_public_id=profile.public_id)
        return profile


class ProspectReviewService:
    """Transitions staff atomiques pour approuver ou refuser une demande."""

    permission = "prospects.review_prospectprofile"

    def _check_actor(self, actor) -> None:
        if not (
            getattr(actor, "is_authenticated", False)
            and getattr(actor, "is_active", False)
            and getattr(actor, "is_staff", False)
            and actor.has_perm("accounts.access_staff_portal")
            and actor.has_perm(self.permission)
        ):
            raise PermissionDenied

    @transaction.atomic
    def approve(
        self,
        *,
        profile_public_id,
        actor,
        review_note: str = "",
        ip_address: str | None = None,
    ) -> ProspectProfile:
        self._check_actor(actor)
        profile = (
            ProspectProfile.objects.select_for_update().filter(public_id=profile_public_id).first()
        )
        if profile is None or profile.status != ProspectProfile.Status.PENDING_REVIEW:
            raise ProspectOnboardingError("Cette demande n'est plus en attente de validation.")

        customer = Customer.objects.create(
            name=profile.company,
            billing_email=profile.email,
            billing_country=profile.country if profile.country != "ZZ" else "",
            shipping_country=profile.country if profile.country != "ZZ" else "",
            siren=profile.siren,
            vat_number=profile.vat_number,
            is_active=False,
        )
        from apps.customers.services.invitations import CustomerInvitationService

        CustomerInvitationService().create_owner_activation(
            customer=customer,
            email=profile.email,
            actor=actor,
        )
        profile.customer = customer
        profile.status = ProspectProfile.Status.APPROVED_PENDING_ACTIVATION
        profile.reviewed_by = actor
        profile.reviewed_at = timezone.now()
        profile.review_note = review_note.strip()
        profile.save(
            update_fields=(
                "customer",
                "status",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "updated_at",
            )
        )
        record_event(
            action="prospect.access_request.approved",
            actor=actor,
            target=profile,
            ip_address=ip_address,
            metadata={"customer_public_id": str(customer.public_id)},
        )
        return profile

    @transaction.atomic
    def reject(
        self,
        *,
        profile_public_id,
        actor,
        rejection_reason: str,
        review_note: str = "",
        ip_address: str | None = None,
    ) -> ProspectProfile:
        self._check_actor(actor)
        profile = (
            ProspectProfile.objects.select_for_update().filter(public_id=profile_public_id).first()
        )
        if profile is None or profile.status != ProspectProfile.Status.PENDING_REVIEW:
            raise ProspectOnboardingError("Cette demande n'est plus en attente de validation.")
        reason = rejection_reason.strip()
        if not reason:
            raise ProspectOnboardingError("Le motif communiqué au prospect est obligatoire.")

        profile.status = ProspectProfile.Status.REJECTED
        profile.is_open = False
        profile.reviewed_by = actor
        profile.reviewed_at = timezone.now()
        profile.review_note = review_note.strip()
        profile.rejection_reason = reason
        profile.save(
            update_fields=(
                "status",
                "is_open",
                "reviewed_by",
                "reviewed_at",
                "review_note",
                "rejection_reason",
                "updated_at",
            )
        )
        record_event(
            action="prospect.access_request.rejected",
            actor=actor,
            target=profile,
            ip_address=ip_address,
        )
        from apps.notifications.services.transactional import (
            schedule_access_request_rejected_email,
        )

        schedule_access_request_rejected_email(profile_public_id=profile.public_id)
        return profile
