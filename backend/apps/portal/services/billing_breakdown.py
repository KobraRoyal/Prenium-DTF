"""Read-only presentation of the order's persisted pricing snapshot."""

from decimal import Decimal

from apps.catalog.models import CatalogService
from apps.customers.services.volume_discounts import linear_meters_from_sqm
from apps.orders.models import Order


def order_billing_breakdown(order):
    priced = order.pricing_status == Order.PricingStatus.PRICED
    result = {"order": order, "priced": priced, "rows": [], "vat_percent": order.tax_rate * 100}
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
