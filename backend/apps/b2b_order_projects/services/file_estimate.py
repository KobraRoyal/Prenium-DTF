"""Estimation indicative des commandes fichier en encours.

Le montant facturé reste celui du métrage réel saisi par l’atelier.
Cette estimation ne modifie ni la commande, ni le moteur de tarification.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Sum
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import Customer
from apps.customers.services.volume_discounts import (
    linear_meters_from_sqm,
    month_bounds,
    pick_tier_for_volume,
    resolve_active_ladder,
)
from apps.orders.models import Order
from apps.orders.services.pricing import (
    FOURPLACES,
    OrderPricingService,
    billable_sqm_from_physical_size,
)
from apps.shipping.services.methods import (
    ShippingMethodService,
    shipping_processing_delay_label,
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
    ladder = []
    month_volume = Decimal("0.0000")
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
        ladder = resolve_active_ladder(customer)
        month_volume = _deferred_priced_linear_m(customer)
        if quote is not None:
            quote = _with_reached_tier(quote, month_volume=month_volume, ladder=ladder)
            quote["shipping_estimate_label"] = _shipping_estimate_label(quote)
    return {
        "quote": quote,
        "requested": bool(project.price_confirmation_required),
        "indicative_linear_m": _indicative_linear_m(quote),
        "laize_m": _laize_m(),
        "priced_month_linear_m": month_volume,
        "volume_ladder": _ladder_token(ladder),
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


def _deferred_priced_linear_m(customer) -> Decimal:
    """Mètres déjà tarifés du mois, même périmètre que le palier rétroactif."""
    from apps.catalog.models import CatalogService
    from apps.orders.models import OrderLine

    _month_start, _next_month, starts_at, ends_at = month_bounds(timezone.localdate())
    eligible = Order.objects.filter(
        customer=customer,
        billing_mode=Order.BillingMode.DEFERRED,
        pricing_status=Order.PricingStatus.PRICED,
        billing_statement__isnull=True,
        status=Order.Status.SUBMITTED,
        created_at__gte=starts_at,
        created_at__lt=ends_at,
    )
    total_sqm = OrderLine.objects.filter(
        order__in=eligible,
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    ).aggregate(total=Sum("quantity"))["total"] or Decimal("0.00")
    return linear_meters_from_sqm(total_sqm)


def _shipping_estimate_label(quote) -> str:
    code = str(quote.get("shipping_method_code") or "").strip()
    method = ShippingMethodService().get_active_by_code(code) if code else None
    if method is not None:
        return shipping_processing_delay_label(method)
    name = str(quote.get("shipping_method_name") or "").strip()
    return name or "Expédition"


def _ladder_token(ladder) -> str:
    parts = []
    for tier in ladder:
        minimum = Decimal(tier.minimum_monthly_linear_m).quantize(FOURPLACES)
        percent = Decimal(tier.discount_percent).quantize(TWOPLACES)
        parts.append(f"{minimum}:{percent}")
    return ",".join(parts)


def _with_reached_tier(quote, *, month_volume: Decimal, ladder) -> dict:
    """Applique le palier atteint au DTF, en laissant le tarif m² brut affiché."""
    additional = linear_meters_from_sqm(Decimal(quote["billable_sqm"]))
    quote_volume = (Decimal(month_volume) + additional).quantize(FOURPLACES, rounding=ROUND_HALF_UP)
    tier = pick_tier_for_volume(ladder=ladder, monthly_volume=quote_volume)
    priced = dict(quote)
    priced["monthly_volume_linear_m"] = quote_volume
    if tier is None or tier.discount_percent <= 0:
        return priced
    percent = Decimal(tier.discount_percent).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    gross = Decimal(quote["dtf_gross_amount_eur"])
    factor = (Decimal("100.00") - percent) / Decimal("100.00")
    net = (gross * factor).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    prep = Decimal(quote["prep_amount_eur"])
    subtotal = (net + prep).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    totals = OrderPricingService().compose_order_totals(
        subtotal_ht=subtotal,
        shipping_ht=Decimal(quote["shipping_amount_eur"]),
        billing_mode=Order.BillingMode.DEFERRED,
    )
    priced["dtf_amount_eur"] = net
    priced["volume_discount_percent"] = percent
    priced["volume_discount_amount_eur"] = (gross - net).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    priced["volume_discount_threshold_linear_m"] = tier.minimum_monthly_linear_m
    priced["subtotal_eur"] = totals["subtotal_amount"]
    priced["tax_amount_eur"] = totals["tax_amount"]
    priced["total_eur"] = totals["total_amount"]
    priced["goods_total_eur"] = totals["subtotal_amount"]
    return priced
