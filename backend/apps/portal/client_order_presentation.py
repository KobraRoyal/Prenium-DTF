from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from django.core.exceptions import ObjectDoesNotExist

from apps.core.public_refs import short_public_ref
from apps.orders.references import order_business_number, order_client_reference
from apps.portal.order_status_presentation import client_order_status, handover_date_label


@dataclass(frozen=True, slots=True)
class ClientOrderIdentity:
    label: str
    reference: str
    note: str
    requested_date: date | None


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
