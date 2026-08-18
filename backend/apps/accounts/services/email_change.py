from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.models import User
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event

SIGNING_SALT = "accounts.email-change"
TOKEN_MAX_AGE_SECONDS = 86400


def _max_age() -> int:
    return max(300, int(getattr(settings, "EMAIL_CHANGE_MAX_AGE_SECONDS", TOKEN_MAX_AGE_SECONDS)))


def _public_origin() -> tuple[str, str]:
    parsed = urlparse(str(getattr(settings, "PUBLIC_BASE_URL", "") or "http://localhost:8080"))
    return parsed.scheme or "https", parsed.netloc or "localhost:8080"


class EmailChangeService:
    """Rectification de l'e-mail de connexion, confirmée sur la nouvelle adresse."""

    def request_change(
        self,
        *,
        user: User,
        new_email: str,
        ip_address: str | None = None,
    ) -> None:
        normalized = self._validate_candidate(user=user, new_email=new_email)
        self._enforce_rate_limit(user)
        token = self._dump_token(user=user, new_email=normalized)
        scheme, domain = _public_origin()
        confirm_path = reverse("portal:email-change-confirm", kwargs={"token": token})
        body = render_to_string(
            "portal/emails/email_change.txt",
            {
                "protocol": scheme,
                "domain": domain,
                "confirm_path": confirm_path,
                "brand_name": str(getattr(settings, "LEGAL_BRAND_NAME", "Prenium DTF")),
            },
        )
        subject = render_to_string("portal/emails/email_change_subject.txt").strip()
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [normalized],
            fail_silently=False,
        )
        record_event(
            action="account.email_change.requested",
            actor=user,
            target=user,
            ip_address=ip_address,
            metadata={"new_email": normalized},
        )

    @transaction.atomic
    def confirm_change(
        self,
        *,
        user: User,
        token: str,
        ip_address: str | None = None,
    ) -> User:
        payload = self._load_token(token)
        if str(payload.get("u") or "") != str(user.public_id):
            raise ValidationError("Ce lien ne correspond pas au compte connecté.")
        if str(payload.get("p") or "") != user.password[-12:]:
            raise ValidationError("Ce lien n’est plus valable. Demandez-en un nouveau.")
        new_email = self._validate_candidate(user=user, new_email=str(payload.get("e") or ""))
        locked = User.objects.select_for_update().get(pk=user.pk)
        previous = locked.email
        locked.email = new_email
        locked.save(update_fields=["email", "updated_at"])
        record_event(
            action="account.email_change.confirmed",
            actor=locked,
            target=locked,
            ip_address=ip_address,
            metadata={"previous_email": previous, "new_email": new_email},
        )
        return locked

    def _validate_candidate(self, *, user: User, new_email: str) -> str:
        normalized = new_email.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValidationError("Indiquez une adresse e-mail valide.")
        if normalized == user.email.strip().lower():
            raise ValidationError("Indiquez une adresse différente de l’e-mail actuel.")
        taken = User.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists()
        if taken:
            raise ValidationError("Cette adresse est déjà utilisée par un autre compte.")
        return normalized

    def _enforce_rate_limit(self, user: User) -> None:
        max_attempts = int(getattr(settings, "EMAIL_CHANGE_RATE_LIMIT_MAX_ATTEMPTS", 5))
        window = int(getattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900))
        key = f"email_change_rl:{user.public_id}"
        try:
            current = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=window)
            current = 1
        if current > max_attempts:
            record_event(
                action="account.email_change.rate_limited",
                actor=user,
                target=user,
                status=AuditLogEntry.Status.FAILURE,
                message="Trop de demandes de changement d’e-mail",
            )
            raise ValidationError("Trop de demandes. Réessayez plus tard.")

    def _dump_token(self, *, user: User, new_email: str) -> str:
        signed = signing.dumps(
            {"u": str(user.public_id), "e": new_email, "p": user.password[-12:]},
            salt=SIGNING_SALT,
        )
        return urlsafe_base64_encode(force_bytes(signed))

    def _load_token(self, token: str) -> dict[str, str]:
        try:
            signed = force_str(urlsafe_base64_decode(token))
            payload = signing.loads(signed, salt=SIGNING_SALT, max_age=_max_age())
        except (ValueError, TypeError, signing.BadSignature, signing.SignatureExpired) as exc:
            raise ValidationError("Ce lien n’est plus valable. Demandez-en un nouveau.") from exc
        if not isinstance(payload, dict):
            raise ValidationError("Ce lien n’est plus valable. Demandez-en un nouveau.")
        return payload
