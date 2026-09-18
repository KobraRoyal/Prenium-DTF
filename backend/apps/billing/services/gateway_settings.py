from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse

from apps.auditlog.services import record_event
from apps.billing.models import Payment, PaymentGatewaySettings
from apps.billing.services.secret_crypto import PaymentSecretCrypto

CHANGE_PERMISSION = "billing.change_paymentgatewaysettings"
VIEW_PERMISSION = "billing.view_paymentgatewaysettings"


def _first_nonempty(*values: str) -> str:
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return ""


def mask_secret(value: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "••••"
    return f"•••• {cleaned[-4:]}"


@dataclass(frozen=True)
class EffectivePaymentConfig:
    paypal_enabled: bool
    stripe_enabled: bool
    paypal_client_id: str
    paypal_client_secret: str
    paypal_webhook_id: str
    stripe_publishable_key: str
    stripe_secret_key: str
    stripe_webhook_secret: str
    source: str
    has_atelier_row: bool

    @property
    def paypal_credentials_ready(self) -> bool:
        return bool(self.paypal_client_id and self.paypal_client_secret)

    @property
    def stripe_credentials_ready(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def paypal_live(self) -> bool:
        return self.paypal_enabled and self.paypal_credentials_ready

    @property
    def stripe_live(self) -> bool:
        return self.stripe_enabled and self.stripe_credentials_ready


@dataclass(frozen=True)
class PaymentGatewaySnapshot:
    paypal_enabled: bool
    stripe_enabled: bool
    paypal_live: bool
    stripe_live: bool
    paypal_client_id: str
    paypal_webhook_id: str
    paypal_secret_hint: str
    stripe_publishable_key: str
    stripe_secret_hint: str
    stripe_webhook_hint: str
    has_paypal_secret: bool
    has_stripe_secret: bool
    has_stripe_webhook_secret: bool
    source: str
    has_atelier_row: bool
    paypal_webhook_url: str
    stripe_webhook_url: str


class PaymentGatewaySettingsService:
    change_permission = CHANGE_PERMISSION
    view_permission = VIEW_PERMISSION

    def __init__(self, crypto: PaymentSecretCrypto | None = None) -> None:
        self.crypto = crypto or PaymentSecretCrypto()

    def current_settings(self) -> PaymentGatewaySettings | None:
        return PaymentGatewaySettings.objects.filter(singleton_key=1).first()

    def effective(self) -> EffectivePaymentConfig:
        row = self.current_settings()
        env_paypal_id = str(getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip()
        env_paypal_secret = str(getattr(settings, "PAYPAL_CLIENT_SECRET", "") or "").strip()
        env_paypal_webhook = str(getattr(settings, "PAYPAL_WEBHOOK_ID", "") or "").strip()
        env_stripe_publishable = str(getattr(settings, "STRIPE_PUBLISHABLE_KEY", "") or "").strip()
        env_stripe_secret = str(getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
        env_stripe_webhook = str(getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or "").strip()

        if row is None:
            paypal_ready = bool(env_paypal_id and env_paypal_secret)
            stripe_ready = bool(env_stripe_secret)
            return EffectivePaymentConfig(
                paypal_enabled=paypal_ready,
                stripe_enabled=stripe_ready,
                paypal_client_id=env_paypal_id,
                paypal_client_secret=env_paypal_secret,
                paypal_webhook_id=env_paypal_webhook,
                stripe_publishable_key=env_stripe_publishable,
                stripe_secret_key=env_stripe_secret,
                stripe_webhook_secret=env_stripe_webhook,
                source="env",
                has_atelier_row=False,
            )

        paypal_secret = _first_nonempty(
            self.crypto.decrypt_or_empty(row.paypal_client_secret_encrypted),
            env_paypal_secret,
        )
        stripe_secret = _first_nonempty(
            self.crypto.decrypt_or_empty(row.stripe_secret_key_encrypted),
            env_stripe_secret,
        )
        stripe_webhook = _first_nonempty(
            self.crypto.decrypt_or_empty(row.stripe_webhook_secret_encrypted),
            env_stripe_webhook,
        )
        return EffectivePaymentConfig(
            paypal_enabled=bool(row.paypal_enabled),
            stripe_enabled=bool(row.stripe_enabled),
            paypal_client_id=_first_nonempty(row.paypal_client_id, env_paypal_id),
            paypal_client_secret=paypal_secret,
            paypal_webhook_id=_first_nonempty(row.paypal_webhook_id, env_paypal_webhook),
            stripe_publishable_key=_first_nonempty(
                row.stripe_publishable_key, env_stripe_publishable
            ),
            stripe_secret_key=stripe_secret,
            stripe_webhook_secret=stripe_webhook,
            source="atelier",
            has_atelier_row=True,
        )

    def configured_providers(self) -> list[str]:
        config = self.effective()
        providers: list[str] = []
        if config.paypal_live:
            providers.append(Payment.Provider.PAYPAL)
        if config.stripe_live:
            providers.append(Payment.Provider.STRIPE)
        return providers

    def webhook_urls(self) -> dict[str, str]:
        base = str(getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
        return {
            "paypal": f"{base}{reverse('billing:backend-paypal-webhook')}",
            "stripe": f"{base}{reverse('billing:backend-stripe-webhook')}",
        }

    def snapshot(self) -> PaymentGatewaySnapshot:
        config = self.effective()
        urls = self.webhook_urls()
        row = self.current_settings()
        has_paypal_secret = bool(
            config.paypal_client_secret
            or (row and row.paypal_client_secret_encrypted)
        )
        has_stripe_secret = bool(
            config.stripe_secret_key or (row and row.stripe_secret_key_encrypted)
        )
        has_stripe_webhook = bool(
            config.stripe_webhook_secret or (row and row.stripe_webhook_secret_encrypted)
        )
        return PaymentGatewaySnapshot(
            paypal_enabled=config.paypal_enabled,
            stripe_enabled=config.stripe_enabled,
            paypal_live=config.paypal_live,
            stripe_live=config.stripe_live,
            paypal_client_id=config.paypal_client_id,
            paypal_webhook_id=config.paypal_webhook_id,
            paypal_secret_hint=mask_secret(config.paypal_client_secret),
            stripe_publishable_key=config.stripe_publishable_key,
            stripe_secret_hint=mask_secret(config.stripe_secret_key),
            stripe_webhook_hint=mask_secret(config.stripe_webhook_secret),
            has_paypal_secret=has_paypal_secret,
            has_stripe_secret=has_stripe_secret,
            has_stripe_webhook_secret=has_stripe_webhook,
            source=config.source,
            has_atelier_row=config.has_atelier_row,
            paypal_webhook_url=urls["paypal"],
            stripe_webhook_url=urls["stripe"],
        )

    def update(
        self,
        *,
        paypal_enabled: bool,
        stripe_enabled: bool,
        paypal_client_id: str,
        paypal_client_secret: str,
        paypal_webhook_id: str,
        stripe_publishable_key: str,
        stripe_secret_key: str,
        stripe_webhook_secret: str,
        actor,
        source: str,
        ip_address: str | None = None,
    ) -> PaymentGatewaySettings:
        if actor is None or not actor.has_perm(self.change_permission):
            raise PermissionDenied

        paypal_secret = str(paypal_client_secret or "").strip()
        stripe_secret = str(stripe_secret_key or "").strip()
        stripe_webhook = str(stripe_webhook_secret or "").strip()
        paypal_id = str(paypal_client_id or "").strip()
        stripe_pk = str(stripe_publishable_key or "").strip()
        existing = self.current_settings()
        env_paypal_id = str(getattr(settings, "PAYPAL_CLIENT_ID", "") or "").strip()
        env_paypal_secret = str(getattr(settings, "PAYPAL_CLIENT_SECRET", "") or "").strip()
        env_stripe_secret = str(getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
        stored_paypal_secret = (
            self.crypto.decrypt_or_empty(existing.paypal_client_secret_encrypted)
            if existing
            else ""
        )
        stored_stripe_secret = (
            self.crypto.decrypt_or_empty(existing.stripe_secret_key_encrypted)
            if existing
            else ""
        )
        paypal_ready = bool(
            (paypal_id or env_paypal_id)
            and (paypal_secret or stored_paypal_secret or env_paypal_secret)
        )
        stripe_ready = bool(stripe_secret or stored_stripe_secret or env_stripe_secret)
        if paypal_enabled and not paypal_ready:
            raise ValidationError(
                {"paypal_client_secret": "Connectez PayPal avant de l’activer."}
            )
        if stripe_enabled and not stripe_ready:
            raise ValidationError(
                {"stripe_secret_key": "Connectez Stripe avant de l’activer."}
            )

        with transaction.atomic():
            row, _created = PaymentGatewaySettings.objects.select_for_update().get_or_create(
                singleton_key=1
            )
            before = {
                "paypal_enabled": row.paypal_enabled,
                "stripe_enabled": row.stripe_enabled,
                "paypal_has_secret": bool(row.paypal_client_secret_encrypted),
                "stripe_has_secret": bool(row.stripe_secret_key_encrypted),
            }
            row.paypal_enabled = bool(paypal_enabled)
            row.stripe_enabled = bool(stripe_enabled)
            row.paypal_client_id = paypal_id
            row.paypal_webhook_id = str(paypal_webhook_id or "").strip()
            row.stripe_publishable_key = stripe_pk
            if paypal_secret:
                row.paypal_client_secret_encrypted = self.crypto.encrypt(paypal_secret)
            if stripe_secret:
                row.stripe_secret_key_encrypted = self.crypto.encrypt(stripe_secret)
            if stripe_webhook:
                row.stripe_webhook_secret_encrypted = self.crypto.encrypt(stripe_webhook)
            row.updated_by = actor
            row.full_clean()
            row.save()

        after = {
            "paypal_enabled": row.paypal_enabled,
            "stripe_enabled": row.stripe_enabled,
            "paypal_has_secret": bool(row.paypal_client_secret_encrypted),
            "stripe_has_secret": bool(row.stripe_secret_key_encrypted),
        }
        record_event(
            action="billing.payment_gateways.updated",
            actor=actor,
            target=row,
            ip_address=ip_address,
            metadata={
                "scope": "global",
                "source": source,
                "before": before,
                "after": after,
                "paypal_secret_rotated": bool(paypal_secret),
                "stripe_secret_rotated": bool(stripe_secret),
                "stripe_webhook_rotated": bool(stripe_webhook),
            },
        )
        return row


payment_gateway_settings_service = PaymentGatewaySettingsService()
