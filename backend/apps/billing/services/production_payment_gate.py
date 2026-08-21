"""Règles de gate paiement / production pour les commandes comptant CB atelier."""

from __future__ import annotations

from decimal import Decimal

from apps.billing.models import Payment
from apps.orders.models import Order


def requires_captured_payment_before_production(order: Order) -> bool:
    """True pour les dépôts atelier en paiement comptant CB."""
    return order.billing_mode == Order.BillingMode.IMMEDIATE and order.uses_atelier_pricing()


def order_has_captured_payment(order: Order) -> bool:
    prefetched_payments = getattr(order, "_captured_payments", None)
    if prefetched_payments is not None:
        return bool(prefetched_payments)
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


def attach_awaits_client_payment(orders: list[Order]) -> list[Order]:
    """Pose ``awaits_client_payment`` sur chaque commande (1 requête Payment)."""
    order_list = list(orders)
    if not order_list:
        return order_list
    captured_ids = set(
        Payment.objects.filter(
            order_id__in=[order.pk for order in order_list],
            status=Payment.Status.CAPTURED,
        ).values_list("order_id", flat=True)
    )
    for order in order_list:
        if order.pk in captured_ids:
            order.awaits_client_payment = False
            continue
        if not requires_captured_payment_before_production(order):
            order.awaits_client_payment = False
            continue
        if order.pricing_status != Order.PricingStatus.PRICED:
            order.awaits_client_payment = False
            continue
        if order.total_amount is None or order.total_amount <= Decimal("0.00"):
            order.awaits_client_payment = False
            continue
        order.awaits_client_payment = True
    return order_list


def count_orders_awaiting_client_payment(customer) -> int:
    """Nombre de commandes client encore à régler (comptant CB atelier)."""
    from django.db.models import Exists, OuterRef

    captured = Payment.objects.filter(
        order_id=OuterRef("pk"),
        status=Payment.Status.CAPTURED,
    )
    candidates = list(
        Order.objects.for_customer(customer)
        .filter(
            billing_mode=Order.BillingMode.IMMEDIATE,
            pricing_status=Order.PricingStatus.PRICED,
            total_amount__gt=Decimal("0.00"),
        )
        .annotate(_has_captured_payment=Exists(captured))
        .filter(_has_captured_payment=False)
        .prefetch_related("items", "uploads")
    )
    return sum(1 for order in candidates if order.uses_atelier_pricing())


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


def should_defer_order_created_until_payment(order: Order) -> bool:
    """Comptant CB atelier : e-mail « commande créée » seulement après capture."""
    return requires_captured_payment_before_production(order)
