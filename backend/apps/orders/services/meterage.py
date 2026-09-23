"""Résolution du métrage atelier (saisie manuelle ou Gang Sheet automatique)."""

from __future__ import annotations

from decimal import Decimal

from apps.customers.services.volume_discounts import linear_meters_from_sqm
from apps.orders.models import Order


def _order_uploads(order: Order) -> list:
    uploads_manager = getattr(order, "uploads", None)
    if uploads_manager is None:
        return []
    try:
        return list(uploads_manager.all())
    except (AttributeError, TypeError):
        return []


def order_uploads_have_surface_overrides(order: Order) -> bool:
    uploads = _order_uploads(order)
    return bool(uploads) and all(upload.meterage_override_sqm is not None for upload in uploads)


def order_meterage_is_resolved(order: Order) -> bool:
    """True si le métrage est connu pour le workflow Atelier (saisie ou auto GS)."""
    if getattr(order, "meterage_override_linear_m", None) is not None:
        return True
    return order_uploads_have_surface_overrides(order)


def resolved_linear_meters(order: Order) -> Decimal | None:
    """Mètres linéaires affichés / figés à l'impression (commande ou dérivés des m²)."""
    linear = getattr(order, "meterage_override_linear_m", None)
    if linear is not None:
        return linear
    uploads = _order_uploads(order)
    if not uploads or not all(upload.meterage_override_sqm is not None for upload in uploads):
        return None
    total_sqm = sum((upload.meterage_override_sqm for upload in uploads), Decimal("0"))
    if total_sqm <= 0:
        return None
    return linear_meters_from_sqm(total_sqm)


def order_pricing_is_payment_frozen(order: Order) -> bool:
    """Tarif figé dès qu'un paiement IMMEDIATE a été lancé (tout statut)."""
    if getattr(order, "billing_mode", None) != Order.BillingMode.IMMEDIATE:
        return False
    payments = getattr(order, "payments", None)
    if payments is None:
        return False
    try:
        return payments.exists()
    except (AttributeError, TypeError):
        return False
