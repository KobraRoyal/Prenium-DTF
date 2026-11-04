"""Estimation indicative des commandes fichier en encours.

Le montant facturé reste celui du métrage réel saisi par l’atelier.
Cette estimation ne modifie ni la commande, ni le moteur de tarification.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError

from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.orders.services.pricing import (
    FOURPLACES,
    OrderPricingService,
    billable_sqm_from_physical_size,
)

TWOPLACES = Decimal("0.01")
QUOTE_CLOSED_STATUSES = {
    B2BOrderProject.Status.SUBMITTED,
    B2BOrderProject.Status.CONVERTED,
    B2BOrderProject.Status.CANCELLED,
    B2BOrderProject.Status.BLOCKED,
}


def is_deferred_file_project(*, project, customer) -> bool:
    billing_mode = getattr(customer, "default_billing_mode", Order.BillingMode.DEFERRED)
    return (
        billing_mode == Customer.DefaultBillingMode.DEFERRED
        and project.order_mode == B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS
    )


def present_project_estimate(*, project, customer, shipping_method_code: str | None = None):
    if not is_deferred_file_project(project=project, customer=customer):
        return None
    items = list(project.items.all().only("width_mm", "height_mm", "quantity"))
    quote = None
    if items:
        try:
            quote = OrderPricingService().estimate_reorder_quote(
                customer=customer,
                items=[
                    {
                        "width_mm": item.width_mm,
                        "height_mm": item.height_mm,
                        "quantity": item.quantity,
                    }
                    for item in items
                ],
                shipping_method_code=shipping_method_code,
                billing_mode=Order.BillingMode.DEFERRED,
            )
        except ValidationError:
            quote = None
    return {
        "quote": quote,
        "requested": bool(project.price_confirmation_required),
        "indicative_linear_m": _indicative_linear_m(quote),
        "laize_m": _laize_m(),
        "intro": False,
    }


def present_deferred_file_intro(*, customer):
    """Encart de la page nouvelle commande, avant qu’un projet existe."""
    from apps.b2b_order_projects.permissions import customer_requires_gang_sheet_orders

    if getattr(customer, "default_billing_mode", "") != Customer.DefaultBillingMode.DEFERRED:
        return None
    if customer_requires_gang_sheet_orders(customer):
        return None
    return {"quote": None, "requested": False, "indicative_linear_m": None, "intro": True}


def can_request_file_order_quote(project) -> bool:
    return not project.converted_order_id and project.status not in QUOTE_CLOSED_STATUSES


def request_file_order_quote(*, project, customer, actor, shipping_method_code: str | None = None):
    if not is_deferred_file_project(project=project, customer=customer):
        raise ValidationError("Cette commande n’accepte pas de devis indicatif.")
    if not can_request_file_order_quote(project):
        raise ValidationError("Le devis ne peut plus être demandé sur cette commande.")
    notice = present_project_estimate(
        project=project,
        customer=customer,
        shipping_method_code=shipping_method_code,
    )
    quote = (notice or {}).get("quote")
    project.price_confirmation_required = True
    update_fields = ["price_confirmation_required", "updated_at"]
    if shipping_method_code:
        project.delivery_method = str(shipping_method_code).strip()
        update_fields.append("delivery_method")
    if quote is not None:
        project.estimated_subtotal = quote["subtotal_eur"]
        project.estimated_tax = quote["tax_amount_eur"]
        project.estimated_total = quote["total_eur"]
        linear_m = _indicative_linear_m(quote)
        project.estimated_length_mm = int((linear_m * Decimal("1000")).quantize(Decimal("1")))
        update_fields.extend(
            [
                "estimated_subtotal",
                "estimated_tax",
                "estimated_total",
                "estimated_length_mm",
            ]
        )
    project.save(update_fields=update_fields)
    from apps.notifications.services.transactional import schedule_quote_requested_emails

    schedule_quote_requested_emails(project_public_id=project.public_id)
    record_event(
        action="b2b_order_project.quote_requested",
        actor=actor,
        target=project,
        message="Devis indicatif demandé avant transmission.",
        metadata={
            "estimated_total": str(project.estimated_total or ""),
            "estimated_length_mm": project.estimated_length_mm,
        },
    )
    return project


def present_order_notice(order):
    """Encart commande déjà transmise : texte, et estimation si le projet fichier existe."""
    if order.billing_mode != Order.BillingMode.DEFERRED:
        return None
    if order.pricing_status == Order.PricingStatus.PRICED:
        return None
    try:
        project = order.source_b2b_order_project
    except ObjectDoesNotExist:
        project = None
    if project is not None and project.order_mode != B2BOrderProject.OrderMode.INDIVIDUAL_DESIGNS:
        return None
    if project is None:
        return {"quote": None, "requested": False, "indicative_linear_m": None}
    return present_project_estimate(project=project, customer=order.customer)


def unit_billable_sqm(*, width_mm, height_mm) -> Decimal:
    """Surface facturable d’un exemplaire, même règle que le devis indicatif."""
    laize_m = _laize_m()
    mode = str(getattr(settings, "DTF_METERAGE_AREA_MODE", "laize_fit") or "laize_fit")
    width_m = (Decimal(str(width_mm)) / Decimal("1000")).quantize(
        FOURPLACES, rounding=ROUND_HALF_UP
    )
    height_m = (Decimal(str(height_mm)) / Decimal("1000")).quantize(
        FOURPLACES, rounding=ROUND_HALF_UP
    )
    return billable_sqm_from_physical_size(
        width_m=width_m,
        height_m=height_m,
        laize_m=laize_m,
        mode=mode,
    )


def _laize_m() -> Decimal:
    laize_cm = Decimal(int(getattr(settings, "DTF_LAIZE_CM", 55)))
    return (laize_cm / Decimal("100")).quantize(FOURPLACES, rounding=ROUND_HALF_UP)


def _indicative_linear_m(quote) -> Decimal | None:
    if not quote or not quote.get("billable_sqm"):
        return None
    laize_m = _laize_m()
    if laize_m <= 0:
        return None
    return (Decimal(quote["billable_sqm"]) / laize_m).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
