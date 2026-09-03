"""Statut opérationnel, lisible et unique pour les listes de commandes."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ObjectDoesNotExist


@dataclass(frozen=True, slots=True)
class OperationalOrderStatus:
    """Projection de lecture : elle ne modifie jamais les statuts métier."""

    key: str
    label: str
    tone: str


_PRODUCTION_STATUSES = {
    "queued": OperationalOrderStatus("queued", "En file Atelier", "is-warning"),
    "in_progress": OperationalOrderStatus("in_progress", "En production", "is-warning"),
    "blocked": OperationalOrderStatus("blocked", "Bloquée", "is-danger"),
    "ready_to_ship": OperationalOrderStatus("ready_to_ship", "Prête à expédier", "is-success"),
    "completed": OperationalOrderStatus("completed", "Terminée", "is-success"),
}

_CLIENT_PRODUCTION_STATUSES = {
    "queued": OperationalOrderStatus("queued", "En préparation", "is-warning"),
    "in_progress": OperationalOrderStatus("in_progress", "En production", "is-warning"),
    "blocked": OperationalOrderStatus("blocked", "En attente de vérification", "is-warning"),
}

_ORDER_STATUSES = {
    "draft": OperationalOrderStatus("draft", "Brouillon", "is-neutral"),
    "submitted": OperationalOrderStatus("submitted", "Soumise", "is-neutral"),
    "cancelled": OperationalOrderStatus("cancelled", "Annulée", "is-danger"),
}


def _related_or_none(instance, relation: str):
    try:
        return getattr(instance, relation, None)
    except ObjectDoesNotExist:
        return None


def is_pickup_order(order) -> bool:
    return str(getattr(order, "shipping_method_code", "") or "").strip().lower() == "pickup"


def handover_date_label(order) -> str:
    """Return the client-facing label for the shared handover date field."""
    return "Retrait prévu" if is_pickup_order(order) else "Livraison prévue"


def client_production_status(
    production_status: str,
    *,
    is_pickup: bool,
) -> OperationalOrderStatus:
    """Translate an Atelier status into the corresponding client-facing step."""
    normalized_status = str(production_status or "").strip().lower()
    if normalized_status == "ready_to_ship":
        if is_pickup:
            return OperationalOrderStatus("ready_for_pickup", "Prête au retrait", "is-success")
        return OperationalOrderStatus("ready_to_ship", "Prête à expédier", "is-success")
    if normalized_status == "completed":
        if is_pickup:
            return OperationalOrderStatus("picked_up", "Retirée", "is-success")
        return OperationalOrderStatus("production_completed", "Préparation terminée", "is-success")
    return _CLIENT_PRODUCTION_STATUSES.get(
        normalized_status,
        OperationalOrderStatus(normalized_status or "unknown", "À suivre", "is-neutral"),
    )


def client_shipment_status(shipment) -> OperationalOrderStatus:
    """Translate the carrier state into a client-facing delivery step."""
    carrier_status = str(getattr(shipment, "sendcloud_status_code", "") or "").strip().upper()
    if carrier_status == "DELIVERED":
        return OperationalOrderStatus("delivered", "Livrée", "is-success")
    return OperationalOrderStatus("shipped", "Expédiée", "is-success")


def client_order_status(order) -> OperationalOrderStatus:
    """Return the single client-facing status for the order's current real-world step."""

    order_status = str(getattr(order, "status", "") or "").strip().lower()
    if order_status == "cancelled":
        return _ORDER_STATUSES["cancelled"]
    if order_status == "draft":
        return _ORDER_STATUSES["draft"]

    pricing_status = str(getattr(order, "pricing_status", "") or "").strip().lower()
    if pricing_status == "failed":
        return OperationalOrderStatus("action_required", "Action requise", "is-danger")
    if pricing_status and pricing_status != "priced":
        return OperationalOrderStatus("pricing_pending", "Tarif à confirmer", "is-warning")

    if bool(getattr(order, "awaits_client_payment", False)):
        return OperationalOrderStatus("awaiting_payment", "Paiement à effectuer", "is-warning")

    shipment = _related_or_none(order, "shipment")
    if shipment is not None and getattr(shipment, "shipped_at", None) is not None:
        return client_shipment_status(shipment)

    production_job = _related_or_none(order, "production_job")
    production_status = str(getattr(production_job, "status", "") or "").strip().lower()
    if production_status:
        return client_production_status(
            production_status,
            is_pickup=is_pickup_order(order),
        )

    if order_status == "submitted":
        return OperationalOrderStatus("submitted", "Commande transmise", "is-neutral")
    return _ORDER_STATUSES.get(
        order_status,
        OperationalOrderStatus(order_status or "unknown", "À suivre", "is-neutral"),
    )


def operational_order_status(order) -> OperationalOrderStatus:
    """Return the one status that describes the order's current real-world step."""

    order_status = str(getattr(order, "status", "") or "").strip().lower()
    if order_status == "cancelled":
        return _ORDER_STATUSES["cancelled"]
    if order_status == "draft":
        return _ORDER_STATUSES["draft"]

    pricing_status = str(getattr(order, "pricing_status", "") or "").strip().lower()
    if pricing_status == "failed":
        return OperationalOrderStatus("pricing_failed", "Tarification à corriger", "is-danger")
    if pricing_status and pricing_status != "priced":
        return OperationalOrderStatus("pricing_pending", "Tarif à confirmer", "is-warning")

    if bool(getattr(order, "awaits_client_payment", False)):
        return OperationalOrderStatus("awaiting_payment", "Paiement à effectuer", "is-warning")

    shipment = _related_or_none(order, "shipment")
    if shipment is not None and getattr(shipment, "shipped_at", None) is not None:
        return OperationalOrderStatus("shipped", "Expédiée", "is-success")

    production_job = _related_or_none(order, "production_job")
    production_status = str(getattr(production_job, "status", "") or "").strip().lower()
    if production_status == "ready_to_ship" and (
        str(getattr(order, "shipping_method_code", "") or "").strip().lower() == "pickup"
    ):
        return OperationalOrderStatus("ready_for_pickup", "Prête au retrait", "is-success")
    if production_status in _PRODUCTION_STATUSES:
        return _PRODUCTION_STATUSES[production_status]

    return _ORDER_STATUSES.get(
        order_status,
        OperationalOrderStatus(order_status or "unknown", "À suivre", "is-neutral"),
    )


def prepare_orders_for_list(orders, *, audience: str = "staff"):
    """Attach the audience-specific display state once for the shared order table."""

    order_list = list(orders or [])
    orders_without_payment_state = [
        order for order in order_list if not hasattr(order, "awaits_client_payment")
    ]
    if orders_without_payment_state:
        from apps.billing.services.production_payment_gate import attach_awaits_client_payment

        attach_awaits_client_payment(orders_without_payment_state)
    for order in order_list:
        order.operational_status = (
            client_order_status(order) if audience == "client" else operational_order_status(order)
        )
        order.handover_date_label = handover_date_label(order)
    return order_list
