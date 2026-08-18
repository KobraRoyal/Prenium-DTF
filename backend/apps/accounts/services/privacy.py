from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.customers.models import (
    CUSTOMER_ROLE_OWNER,
    Customer,
    CustomerInvitation,
    CustomerMembership,
)
from apps.orders.models import Order
from apps.prospects.models import ProspectProfile

User = get_user_model()

ANONYMIZED_NAME = "Anonymisé"
CLOSED_EMAIL_DOMAIN = "invalid.localhost"


class PrivacyRightsService:
    """Export et clôture du compte personne physique, sans casser la comptabilité."""

    def export_user_data(self, *, user: User) -> dict[str, object]:
        memberships = list(
            CustomerMembership.objects.filter(user=user)
            .select_related("customer")
            .order_by("customer__name")
        )
        customer_ids = [membership.customer_id for membership in memberships]
        orders = (
            Order.objects.filter(created_by=user, customer_id__in=customer_ids).order_by(
                "-created_at"
            )
            if customer_ids
            else Order.objects.none()
        )
        prospects = ProspectProfile.objects.filter(email__iexact=user.email).order_by("-created_at")
        invitations = CustomerInvitation.objects.filter(email__iexact=user.email).order_by(
            "-created_at"
        )
        return {
            "exported_at": timezone.now().isoformat(),
            "user": {
                "public_id": str(user.public_id),
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "date_joined": user.date_joined.isoformat() if user.date_joined else "",
                "last_login": user.last_login.isoformat() if user.last_login else "",
            },
            "memberships": [
                {
                    "membership_public_id": str(membership.public_id),
                    "customer_public_id": str(membership.customer.public_id),
                    "customer_name": membership.customer.name,
                    "role": membership.role,
                    "is_active": membership.is_active,
                }
                for membership in memberships
            ],
            "customers": [
                self._serialize_customer(membership.customer)
                for membership in memberships
                if membership.is_active and membership.customer.is_active
            ],
            "orders_created": [
                {
                    "public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "status": order.status,
                    "billing_mode": order.billing_mode,
                    "total_amount": str(order.total_amount),
                    "currency": order.currency,
                    "created_at": order.created_at.isoformat(),
                }
                for order in orders.select_related("customer")[:200]
            ],
            "access_requests": [
                {
                    "public_id": str(profile.public_id),
                    "company": profile.company,
                    "status": profile.status,
                    "submitted_at": (
                        profile.submitted_at.isoformat() if profile.submitted_at else ""
                    ),
                }
                for profile in prospects
            ],
            "invitations": [
                {
                    "public_id": str(invitation.public_id),
                    "customer_public_id": str(invitation.customer.public_id),
                    "role": invitation.role,
                    "status": invitation.status,
                }
                for invitation in invitations.select_related("customer")
            ],
        }

    def export_user_data_json(self, *, user: User) -> bytes:
        payload = self.export_user_data(user=user)
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    @transaction.atomic
    def close_account(self, *, user: User, actor, ip_address: str | None = None) -> User:
        locked = User.objects.select_for_update().get(pk=user.pk)
        if not locked.is_active:
            raise ValidationError("Ce compte est déjà clôturé.")
        if locked.is_staff or locked.has_perm("accounts.access_staff_portal"):
            raise ValidationError(
                "Un compte atelier ne peut pas être clôturé en libre-service. "
                "Contactez un administrateur."
            )

        memberships = list(
            CustomerMembership.objects.select_for_update()
            .select_related("customer")
            .filter(user=locked, is_active=True)
        )
        for membership in memberships:
            membership.is_active = False
            membership.save(update_fields=("is_active", "updated_at"))
            if membership.role == CUSTOMER_ROLE_OWNER:
                remaining_owners = (
                    CustomerMembership.objects.filter(
                        customer=membership.customer,
                        role=CUSTOMER_ROLE_OWNER,
                        is_active=True,
                    )
                    .exclude(pk=membership.pk)
                    .exists()
                )
                if not remaining_owners:
                    Customer.objects.filter(pk=membership.customer_id).update(
                        is_active=False,
                        updated_at=timezone.now(),
                    )

        CustomerInvitation.objects.filter(
            email__iexact=locked.email,
            status=CustomerInvitation.Status.PENDING,
        ).update(
            status=CustomerInvitation.Status.REVOKED,
            revoked_at=timezone.now(),
            updated_at=timezone.now(),
        )

        original_email = locked.email
        self._anonymize_prospects(email=original_email)
        closed_email = f"deleted-{locked.public_id}@{CLOSED_EMAIL_DOMAIN}"
        locked.email = closed_email
        locked.first_name = ANONYMIZED_NAME
        locked.last_name = ANONYMIZED_NAME
        locked.is_active = False
        locked.set_unusable_password()
        locked.save(
            update_fields=(
                "email",
                "first_name",
                "last_name",
                "is_active",
                "password",
                "updated_at",
            )
        )
        record_event(
            action="account.privacy.closed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=locked,
            ip_address=ip_address,
            metadata={"user_public_id": str(locked.public_id)},
        )
        return locked

    def _serialize_customer(self, customer) -> dict[str, object]:
        return {
            "public_id": str(customer.public_id),
            "name": customer.name,
            "billing_email": customer.billing_email,
            "billing_city": customer.billing_city,
            "billing_country": customer.billing_country,
            "shipping_city": customer.shipping_city,
            "shipping_country": customer.shipping_country,
        }

    def _anonymize_prospects(self, *, email: str) -> None:
        closed_at = timezone.now()
        for profile in ProspectProfile.objects.select_for_update().filter(email__iexact=email):
            profile.first_name = ANONYMIZED_NAME
            profile.last_name = ANONYMIZED_NAME
            profile.phone = ""
            profile.email = f"deleted-prospect-{profile.public_id}@{CLOSED_EMAIL_DOMAIN}"
            profile.normalized_email = profile.email
            profile.is_open = False
            if profile.status in {
                ProspectProfile.Status.PENDING_EMAIL_VERIFICATION,
                ProspectProfile.Status.PENDING_REVIEW,
                ProspectProfile.Status.NEEDS_INFORMATION,
            }:
                profile.status = ProspectProfile.Status.CANCELLED
            profile.save(
                update_fields=(
                    "first_name",
                    "last_name",
                    "phone",
                    "email",
                    "normalized_email",
                    "is_open",
                    "status",
                    "updated_at",
                )
            )
            record_event(
                action="account.privacy.prospect_anonymized",
                target=profile,
                metadata={"closed_at": closed_at.isoformat()},
            )


def redact_recipient_snapshot(recipient: dict | None) -> dict:
    if not isinstance(recipient, dict):
        return {}
    redacted = dict(recipient)
    for field_name in (
        "name",
        "company_name",
        "address_line_1",
        "address_line_2",
        "house_number",
        "email",
        "phone_number",
    ):
        if redacted.get(field_name):
            redacted[field_name] = "[redacted]"
    return redacted


def privacy_safe_shipment_request(payload: dict) -> dict:
    safe = dict(payload)
    if isinstance(payload.get("recipient"), dict):
        safe["recipient"] = redact_recipient_snapshot(payload["recipient"])
    return safe


_PAYMENT_PAYLOAD_KEYS = {
    "id",
    "status",
    "state",
    "object",
    "mode",
    "payment_status",
    "payment_intent",
}


def sanitize_provider_payload(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        return {}
    sanitized: dict[str, object] = {}
    for key in _PAYMENT_PAYLOAD_KEYS:
        value = payload.get(key)
        if isinstance(value, dict) and "id" in value:
            sanitized[key] = {"id": value.get("id")}
        elif value not in (None, ""):
            sanitized[key] = value
    return sanitized


def apply_privacy_retention(
    *,
    now=None,
    audit_ip_days: int,
    payment_payload_days: int,
    shipment_snapshot_days: int,
    prospect_pii_days: int,
) -> dict[str, int]:
    from apps.billing.models import Payment
    from apps.shipping.models import Shipment

    moment = now or timezone.now()
    stats = {
        "audit_ips_cleared": 0,
        "payment_payloads_cleared": 0,
        "shipment_snapshots_redacted": 0,
        "prospects_anonymized": 0,
    }

    audit_cutoff = moment - timedelta(days=max(1, audit_ip_days))
    stats["audit_ips_cleared"] = AuditLogEntry.objects.filter(
        ip_address__isnull=False,
        created_at__lt=audit_cutoff,
    ).update(ip_address=None)

    payment_cutoff = moment - timedelta(days=max(1, payment_payload_days))
    stale_payments = Payment.objects.filter(updated_at__lt=payment_cutoff).exclude(
        provider_payload={}
    )
    updated_payments = 0
    for payment in stale_payments.iterator():
        sanitized = sanitize_provider_payload(payment.provider_payload)
        if sanitized != payment.provider_payload:
            payment.provider_payload = sanitized
            payment.save(update_fields=("provider_payload", "updated_at"))
            updated_payments += 1
    stats["payment_payloads_cleared"] = updated_payments

    shipment_cutoff = moment - timedelta(days=max(1, shipment_snapshot_days))
    stale_shipments = Shipment.objects.filter(updated_at__lt=shipment_cutoff)
    redacted_shipments = 0
    for shipment in stale_shipments.iterator():
        snapshot = shipment.request_snapshot or {}
        recipient = snapshot.get("recipient")
        if not isinstance(recipient, dict):
            continue
        safe = privacy_safe_shipment_request(snapshot)
        if safe != snapshot:
            shipment.request_snapshot = safe
            shipment.save(update_fields=("request_snapshot", "updated_at"))
            redacted_shipments += 1
    stats["shipment_snapshots_redacted"] = redacted_shipments

    prospect_cutoff = moment - timedelta(days=max(1, prospect_pii_days))
    stale_prospects = ProspectProfile.objects.filter(
        updated_at__lt=prospect_cutoff,
        status__in={
            ProspectProfile.Status.REJECTED,
            ProspectProfile.Status.EXPIRED,
            ProspectProfile.Status.CANCELLED,
        },
    ).exclude(email__iendswith=f"@{CLOSED_EMAIL_DOMAIN}")
    anonymized = 0
    for profile in stale_prospects.iterator():
        if profile.phone or not profile.email.endswith(f"@{CLOSED_EMAIL_DOMAIN}"):
            profile.first_name = ANONYMIZED_NAME
            profile.last_name = ANONYMIZED_NAME
            profile.phone = ""
            profile.email = f"deleted-prospect-{profile.public_id}@{CLOSED_EMAIL_DOMAIN}"
            profile.normalized_email = profile.email
            profile.is_open = False
            profile.save(
                update_fields=(
                    "first_name",
                    "last_name",
                    "phone",
                    "email",
                    "normalized_email",
                    "is_open",
                    "updated_at",
                )
            )
            anonymized += 1
    stats["prospects_anonymized"] = anonymized
    return stats
