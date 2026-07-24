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


def resolve_online_provider(*, customer, requested_provider: str | None = None) -> str:
    """Choisit PayPal ou Stripe pour un paiement immédiat (hors facturation mensuelle)."""
    preferred = getattr(customer, "preferred_settlement_method", "") or ""
    requested = (requested_provider or "").strip().lower()

    if requested:
        if requested not in {Payment.Provider.PAYPAL, Payment.Provider.STRIPE}:
            raise ValidationError("Moyen de paiement en ligne non supporté.")
        return requested

    if preferred == customer.PreferredSettlementMethod.STRIPE:
        return Payment.Provider.STRIPE
    if preferred == customer.PreferredSettlementMethod.PAYPAL:
        return Payment.Provider.PAYPAL
    if preferred == customer.PreferredSettlementMethod.WIRE_TRANSFER:
        raise ValidationError(
            "Ce compte est configuré en virement bancaire : pas de paiement en ligne."
        )

    # Défaut technique : PayPal si credentials, sinon Stripe.
    if settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET:
        return Payment.Provider.PAYPAL
    if settings.STRIPE_SECRET_KEY:
        return Payment.Provider.STRIPE
    raise ValidationError("Aucun moyen de paiement en ligne n'est configuré.")


def get_payment_gateway(provider: str) -> PaymentGateway:
    if provider == Payment.Provider.PAYPAL:
        from apps.billing.services.paypal import PayPalGateway

        return PayPalGateway()
    if provider == Payment.Provider.STRIPE:
        from apps.billing.services.stripe_gateway import StripeGateway

        return StripeGateway()
    raise ValidationError(f"Provider de paiement inconnu: {provider}")
