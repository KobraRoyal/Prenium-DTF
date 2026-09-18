from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib import request as urllib_request
from urllib.parse import urlsplit

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


class PaymentGatewayTransientError(PaymentGatewayError):
    """L'état distant est inconnu ; le prestataire doit être interrogé à nouveau."""


class PaymentGatewayConfigurationError(PaymentGatewayError):
    pass


class _RejectProviderRedirect(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise PaymentGatewayError("Redirection d'une requête API de paiement refusée.")


def open_provider_request(http_request, *, timeout: int):
    """Empêche urllib de relayer un en-tête Authorization après une redirection."""
    opener = urllib_request.build_opener(_RejectProviderRedirect())
    return opener.open(http_request, timeout=timeout)


def validate_provider_checkout_url(*, url: str, provider: str, allowed_hosts: set[str]) -> str:
    """Accept only the HTTPS checkout origin owned by the selected provider."""
    cleaned = str(url or "").strip()
    parsed = urlsplit(cleaned)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    try:
        port = parsed.port
    except ValueError:
        port = -1
    if (
        parsed.scheme != "https"
        or hostname not in allowed_hosts
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise PaymentGatewayError(f"URL de paiement {provider} invalide.")
    return cleaned


class PaymentGateway(Protocol):
    provider: str

    def create_checkout(
        self,
        *,
        order: Order,
        success_url: str,
        cancel_url: str,
        idempotency_key: str = "",
    ) -> CheckoutCreateResult: ...

    def confirm_checkout(self, *, provider_payment_id: str) -> CheckoutConfirmResult: ...


def configured_online_providers() -> list[str]:
    """Providers réellement proposés au checkout (activés + credentials)."""
    from apps.billing.services.gateway_settings import payment_gateway_settings_service

    return payment_gateway_settings_service.configured_providers()


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
