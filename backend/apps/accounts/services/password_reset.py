from __future__ import annotations

from uuid import UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event

User = get_user_model()


class PasswordResetService:
    """Demande et confirmation de réinitialisation, sans fuite d'existence de compte."""

    def request_reset(self, *, email: str, ip_address: str | None = None) -> None:
        normalized_email = (email or "").strip().lower()
        throttled = self._email_throttled(normalized_email)
        user = None if throttled else self._eligible_user(normalized_email)
        sent = False
        if user is not None:
            uidb64, token = self.make_token_parts(user)
            from apps.notifications.services.transactional import schedule_password_reset_email

            schedule_password_reset_email(
                user_public_id=user.public_id,
                uidb64=uidb64,
                token=token,
            )
            sent = True
        record_event(
            action="security.password_reset.requested",
            actor=user,
            target=user,
            status=AuditLogEntry.Status.SUCCESS,
            message="Demande de réinitialisation de mot de passe",
            ip_address=ip_address,
            metadata={
                "email": normalized_email,
                "sent": sent,
                "throttled": throttled,
            },
        )

    def resolve_user(self, uidb64: str):
        try:
            public_id = UUID(force_str(urlsafe_base64_decode(uidb64)))
        except (ValueError, TypeError, OverflowError, UnicodeDecodeError):
            return None
        return User.objects.filter(public_id=public_id, is_active=True).first()

    def make_token_parts(self, user) -> tuple[str, str]:
        uidb64 = urlsafe_base64_encode(force_bytes(str(user.public_id)))
        token = default_token_generator.make_token(user)
        return uidb64, token

    def reset_path(self, *, uidb64: str, token: str) -> str:
        return reverse(
            "portal:password-reset-confirm",
            kwargs={"uidb64": uidb64, "token": token},
        )

    def complete_reset(self, *, user, password: str, ip_address: str | None = None):
        user.set_password(password)
        user.save(update_fields=["password", "updated_at"])
        record_event(
            action="security.password_reset.completed",
            actor=user,
            target=user,
            ip_address=ip_address,
            metadata={"user_public_id": str(user.public_id)},
        )
        return user

    def _eligible_user(self, normalized_email: str):
        if not normalized_email:
            return None
        user = User.objects.filter(email__iexact=normalized_email, is_active=True).first()
        if user is None or not user.has_usable_password():
            return None
        return user

    def _email_throttled(self, normalized_email: str) -> bool:
        if not normalized_email:
            return True
        max_attempts = getattr(settings, "PASSWORD_RESET_EMAIL_MAX_ATTEMPTS", 3)
        window = getattr(settings, "PASSWORD_RESET_EMAIL_WINDOW_SECONDS", 3600)
        key = f"pwd_reset_email:{normalized_email}"
        try:
            current = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=window)
            current = 1
        return current > max_attempts


password_reset_service = PasswordResetService()
