from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.billing.models import Payment
from apps.orders.models import Order


@dataclass(frozen=True)
class CheckoutCreateResult:
    provider_payment_id: str
    status: str
    checkout_url: str
    payload: dict[str, object]
    provider_capture_id: str = ""


@dataclass(frozen=True)
class CheckoutConfirmResult:
    provider_payment_id: str
    provider_capture_id: str
    status: str
    payload: dict[str, object]
    amount_total_cents: int | None = None
    currency: str | None = None


class PaymentGatewayError(Exception):
    """Erreur provider normalisée pour le PaymentService."""


class PaymentGatewayConfigurationError(PaymentGatewayError):
    pass


class PaymentGateway(Protocol):
    provider: str

    def create_checkout(
        self,
        *,
        order: Order,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutCreateResult: ...

    def confirm_checkout(self, *, provider_payment_id: str) -> CheckoutConfirmResult: ...


def configured_online_providers() -> list[str]:
    """Providers réellement installés (credentials présents)."""
    providers: list[str] = []
    if settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET:
        providers.append(Payment.Provider.PAYPAL)
    if settings.STRIPE_SECRET_KEY:
        providers.append(Payment.Provider.STRIPE)
    return providers


def resolve_online_provider(*, customer, requested_provider: str | None = None) -> str:
    """
    Résout le provider pour un paiement immédiat.

    Le client choisit parmi les moyens installés sur le projet.
    `preferred_settlement_method` sert seulement de pré-sélection, pas de verrou.
    """
    available = configured_online_providers()
    if not available:
        raise ValidationError("Aucun moyen de paiement en ligne n'est configuré.")

    requested = (requested_provider or "").strip().lower()
    if requested:
        if requested not in {Payment.Provider.PAYPAL, Payment.Provider.STRIPE}:
            raise ValidationError("Moyen de paiement en ligne non supporté.")
        if requested not in available:
            raise ValidationError("Ce moyen de paiement n'est pas disponible sur cette plateforme.")
        return requested

    preferred = getattr(customer, "preferred_settlement_method", "") or ""
    if preferred in available:
        return preferred
    if len(available) == 1:
        return available[0]
    raise ValidationError("Choisissez un moyen de paiement (PayPal ou carte / Stripe).")


def get_payment_gateway(provider: str) -> PaymentGateway:
    if provider == Payment.Provider.PAYPAL:
        from apps.billing.services.paypal import PayPalGateway

        return PayPalGateway()
    if provider == Payment.Provider.STRIPE:
        from apps.billing.services.stripe_gateway import StripeGateway

        return StripeGateway()
    raise ValidationError(f"Provider de paiement inconnu: {provider}")
