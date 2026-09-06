from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime

from django.core.exceptions import ObjectDoesNotExist

from apps.core.public_refs import short_public_ref
from apps.orders.references import order_business_number, order_client_reference
from apps.portal.order_status_presentation import (
    client_order_status,
    client_production_status,
    client_shipment_status,
    handover_date_label,
    is_pickup_order,
)


@dataclass(frozen=True, slots=True)
class ClientOrderIdentity:
    label: str
    reference: str
    note: str
    requested_date: date | None


@dataclass(frozen=True, slots=True)
class ClientOrderShippingPanel:
    """Client-safe presentation of the fulfilment information for an order."""

    key: str
    title: str
    message: str
    event_label: str
    event_at: date | datetime | None
    event_has_time: bool
    tracking_number: str
    tracking_url: str
    last_updated_at: datetime | None
    is_pickup: bool
    is_carrier_handoff: bool


def client_order_identity(order) -> ClientOrderIdentity:
    """Build the stable client-facing identity shared by the page and HTMX panels."""
    label = order_client_reference(order)
    business_number = order_business_number(order)
    try:
        project = order.source_b2b_order_project
    except ObjectDoesNotExist:
        project = None

    if project is not None:
        return ClientOrderIdentity(
            label=label,
            reference=business_number,
            note=project.customer_comment.strip(),
            requested_date=project.requested_date,
        )

    note_lines = (order.customer_note or "").strip().splitlines()
    if label and note_lines and note_lines[0].strip() == label:
        note_lines = note_lines[1:]
    return ClientOrderIdentity(
        label=label,
        reference=business_number,
        note="\n".join(line.strip() for line in note_lines if line.strip()),
        requested_date=None,
    )


def _related_or_none(instance, relation: str):
    try:
        return getattr(instance, relation, None)
    except ObjectDoesNotExist:
        return None


def _pickup_shipping_panel(order) -> ClientOrderShippingPanel:
    """Present a collection order without leaking carrier information."""

    production_job = _related_or_none(order, "production_job")
    expected_at = getattr(order, "estimated_handover_date", None)
    if production_job is None:
        return ClientOrderShippingPanel(
            key="pickup_pending",
            title="Retrait en préparation",
            message=(
                "Nous vous préviendrons dès que votre commande pourra être récupérée à l’atelier."
            ),
            event_label="Retrait prévu" if expected_at else "",
            event_at=expected_at,
            event_has_time=False,
            tracking_number="",
            tracking_url="",
            last_updated_at=None,
            is_pickup=True,
            is_carrier_handoff=False,
        )

    status = client_production_status(
        getattr(production_job, "status", ""),
        is_pickup=True,
    )
    if status.key == "picked_up":
        return ClientOrderShippingPanel(
            key="pickup_collected",
            title="Commande retirée",
            message="Retrait confirmé par l’atelier.",
            event_label="Retrait effectué" if production_job.completed_at else "",
            event_at=production_job.completed_at,
            event_has_time=True,
            tracking_number="",
            tracking_url="",
            last_updated_at=None,
            is_pickup=True,
            is_carrier_handoff=False,
        )
    if status.key == "ready_for_pickup":
        return ClientOrderShippingPanel(
            key="pickup_ready",
            title="Prête au retrait",
            message="Disponible à l’atelier.",
            event_label="Retrait prévu" if expected_at else "",
            event_at=expected_at,
            event_has_time=False,
            tracking_number="",
            tracking_url="",
            last_updated_at=None,
            is_pickup=True,
            is_carrier_handoff=False,
        )

    messages = {
        "in_progress": (
            "Votre commande est en production. Nous vous préviendrons dès qu’elle sera prête au "
            "retrait."
        ),
        "blocked": "L’atelier vérifie votre commande avant de confirmer le retrait.",
    }
    return ClientOrderShippingPanel(
        key=f"pickup_{status.key}",
        title="Retrait en préparation",
        message=messages.get(
            status.key,
            "Nous vous préviendrons dès que votre commande pourra être récupérée à l’atelier.",
        ),
        event_label="Retrait prévu" if expected_at else "",
        event_at=expected_at,
        event_has_time=False,
        tracking_number="",
        tracking_url="",
        last_updated_at=None,
        is_pickup=True,
        is_carrier_handoff=False,
    )


def _delivery_shipping_panel(order, shipment) -> ClientOrderShippingPanel:
    """Translate carrier data into concise client-facing delivery information."""

    expected_at = getattr(order, "estimated_handover_date", None)
    if shipment is None:
        return ClientOrderShippingPanel(
            key="delivery_pending",
            title="Expédition en préparation",
            message="Le suivi apparaîtra dès la prise en charge de votre commande.",
            event_label="Livraison prévue" if expected_at else "",
            event_at=expected_at,
            event_has_time=False,
            tracking_number="",
            tracking_url="",
            last_updated_at=None,
            is_pickup=False,
            is_carrier_handoff=False,
        )

    tracking_number = str(getattr(shipment, "tracking_number", "") or "").strip()
    tracking_url = str(getattr(shipment, "tracking_url", "") or "").strip()
    last_updated_at = getattr(shipment, "last_api_sync_at", None)
    shipped_at = getattr(shipment, "shipped_at", None)
    if shipped_at is None:
        return ClientOrderShippingPanel(
            key="delivery_preparing",
            title="Envoi en préparation",
            message=(
                "Votre numéro de suivi est prêt. Il s’activera dès la prise en charge."
                if tracking_number
                else "Le suivi apparaîtra dès la prise en charge de votre commande."
            ),
            event_label="Livraison prévue" if expected_at else "",
            event_at=expected_at,
            event_has_time=False,
            tracking_number=tracking_number,
            tracking_url=tracking_url,
            last_updated_at=last_updated_at,
            is_pickup=False,
            is_carrier_handoff=False,
        )

    status = client_shipment_status(shipment)
    is_delivered = status.key == "delivered"
    return ClientOrderShippingPanel(
        key="delivery_delivered" if is_delivered else "delivery_in_transit",
        title="Commande livrée" if is_delivered else "Commande en route",
        message=(
            "La livraison a été confirmée." if is_delivered else "Votre colis a été pris en charge."
        ),
        event_label="Prise en charge",
        event_at=shipped_at,
        event_has_time=True,
        tracking_number=tracking_number,
        tracking_url=tracking_url,
        last_updated_at=last_updated_at if last_updated_at != shipped_at else None,
        is_pickup=False,
        is_carrier_handoff=True,
    )


def client_order_shipping_panel(*, order, shipment) -> ClientOrderShippingPanel:
    """Return the appropriate Client panel for collection or carrier delivery."""

    if is_pickup_order(order):
        return _pickup_shipping_panel(order)
    return _delivery_shipping_panel(order, shipment)


def build_client_order_context(
    *,
    customer,
    customer_membership,
    order,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the shared client order context used by the page and its panels."""
    identity = client_order_identity(order)
    context: dict[str, object] = {
        "customer": customer,
        "customer_membership": customer_membership,
        "order": order,
        "order_short_ref": short_public_ref(order.public_id),
        "order_client_label": identity.label,
        "order_display_ref": identity.reference,
        "order_note_details": identity.note,
        "order_requested_date": identity.requested_date,
        "client_order_status": client_order_status(order),
        "handover_date_label": handover_date_label(order),
    }
    context.update(extra or {})
    return context


@dataclass(frozen=True, slots=True)
class ClientOrderStatusBanner:
    tone: str
    message: str
    show_pay_cta: bool


def client_order_status_banner(
    *,
    awaits_client_payment: bool,
    query_params: Mapping[str, str],
) -> ClientOrderStatusBanner | None:
    paid = query_params.get("paid") == "1"
    cancelled = query_params.get("cancelled") == "1"
    checkout_success = query_params.get("checkout") == "success"

    if paid:
        return ClientOrderStatusBanner(
            tone="success",
            message="Paiement confirmé. Le justificatif est dans Règlement.",
            show_pay_cta=False,
        )
    if cancelled:
        return ClientOrderStatusBanner(
            tone="warning",
            message="Paiement non finalisé.",
            show_pay_cta=True,
        )
    if checkout_success and awaits_client_payment:
        return ClientOrderStatusBanner(
            tone="warning",
            message="Commande enregistrée — paiement non finalisé.",
            show_pay_cta=True,
        )
    if checkout_success:
        return ClientOrderStatusBanner(
            tone="success",
            message="Commande transmise.",
            show_pay_cta=False,
        )
    if awaits_client_payment:
        return ClientOrderStatusBanner(
            tone="warning",
            message="Cette commande attend votre paiement.",
            show_pay_cta=True,
        )
    return None
