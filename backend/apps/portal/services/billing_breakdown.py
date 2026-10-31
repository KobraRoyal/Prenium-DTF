"""Read-only presentation of the order's persisted pricing snapshot."""

from decimal import ROUND_HALF_UP, Decimal

from apps.catalog.models import CatalogService
from apps.customers.services.volume_discounts import linear_meters_from_sqm
from apps.orders.models import Order

TWOPLACES = Decimal("0.01")
DISPLAY_VAT_RATE = Decimal("0.20")


def order_vat_preview(order) -> dict[str, Decimal | bool]:
    """TVA affichée. Si le taux enregistré est nul, montre 20 % sans changer le HT encours."""

    subtotal = Decimal(order.subtotal_amount or 0)
    shipping = Decimal(order.shipping_amount or 0)
    total_ht = (subtotal + shipping).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    stored_rate = Decimal(order.tax_rate or 0)
    if stored_rate > 0:
        tax_amount = Decimal(order.tax_amount or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        total_ttc = Decimal(order.total_amount or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        rate = stored_rate
        preview_only = False
    else:
        rate = DISPLAY_VAT_RATE
        tax_amount = (total_ht * rate).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        total_ttc = (total_ht + tax_amount).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        preview_only = True
    return {
        "vat_percent": (rate * Decimal("100")).quantize(TWOPLACES, rounding=ROUND_HALF_UP),
        "displayed_rate": rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        "tax_amount": tax_amount,
        "total_ttc": total_ttc,
        "total_ht": total_ht,
        "vat_preview_only": preview_only,
    }


def order_billing_breakdown(order):
    priced = order.pricing_status == Order.PricingStatus.PRICED
    result = {"order": order, "priced": priced, "rows": [], **order_vat_preview(order)}
    if not priced:
        return result

    lines = list(order.items.all())
    dtf_lines = [
        line for line in lines if line.service_type == CatalogService.ServiceType.DTF_TRANSFER
    ]
    atelier = bool(dtf_lines) and order.uses_atelier_pricing()
    # Atelier quantities are stored in m², despite the catalogue's linear-meter unit.
    discount = order.volume_discount_amount or Decimal("0")
    base_price = order.volume_discount_base_unit_price_eur
    separate_discount = atelier and discount > 0 and base_price is not None
    result.update(discount=discount, separate_discount=separate_discount)
    if atelier:
        quantity = sum((line.quantity for line in dtf_lines), Decimal("0"))
        prices = {line.unit_price for line in dtf_lines}
        result["rows"].append(
            {
                "label": "Impression DTF",
                "quantity": quantity,
                "unit": "m²",
                "unit_price": base_price
                if separate_discount
                else (prices.pop() if len(prices) == 1 else None),
                "amount": sum((line.line_total for line in dtf_lines), Decimal("0"))
                + (discount if separate_discount else 0),
                "linear_m": order.meterage_override_linear_m
                if order.meterage_override_linear_m is not None
                else linear_meters_from_sqm(quantity),
                "visual_count": len(dtf_lines),
            }
        )
    for line in lines:
        if atelier and line in dtf_lines:
            continue
        preparation = line.service_type == CatalogService.ServiceType.FILE_PREPARATION
        result["rows"].append(
            {
                "label": "Préparation des fichiers" if preparation else line.service_name,
                "quantity": line.quantity,
                "unit": "fichier(s)"
                if preparation
                else (
                    "m linéaires" if line.unit == CatalogService.Unit.LINEAR_METER else "unité(s)"
                ),
                "unit_price": line.unit_price,
                "amount": line.line_total,
            }
        )
    return result
