"""Règles de gate paiement / production pour les commandes comptant CB atelier."""

from __future__ import annotations

from decimal import Decimal

from apps.billing.models import Payment
from apps.orders.models import Order


def requires_captured_payment_before_production(order: Order) -> bool:
    """True pour les dépôts atelier en paiement comptant CB."""
    return (
        order.billing_mode == Order.BillingMode.IMMEDIATE
        and order.uses_atelier_pricing()
    )


def order_has_captured_payment(order: Order) -> bool:
    return Payment.objects.filter(
        order_id=order.pk,
        status=Payment.Status.CAPTURED,
    ).exists()


def order_awaits_client_payment(order: Order) -> bool:
    """Commande tarifée comptant CB, en attente du règlement client."""
    if not requires_captured_payment_before_production(order):
        return False
    if order.pricing_status != Order.PricingStatus.PRICED:
        return False
    if order.total_amount is None or order.total_amount <= Decimal("0.00"):
        return False
    return not order_has_captured_payment(order)


def production_start_blocked_reason(order: Order) -> str | None:
    """Motif de refus du lancement production, ou None si autorisé."""
    if not requires_captured_payment_before_production(order):
        return None
    if order_has_captured_payment(order):
        return None
    if order.pricing_status != Order.PricingStatus.PRICED:
        return (
            "Commande comptant CB : calculez le métrage / tarif atelier, "
            "puis attendez le paiement client avant de lancer la production."
        )
    return (
        "Commande comptant CB : le paiement client doit être confirmé "
        "avant de lancer la production."
    )
