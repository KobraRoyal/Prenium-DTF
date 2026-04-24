from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from apps.catalog.models import CatalogService

TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class PriceQuote:
    service: CatalogService
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class PricingService:
    def normalize_quantity(self, service: CatalogService, raw_quantity) -> Decimal:
        try:
            quantity = Decimal(str(raw_quantity)).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError):
            raise ValidationError("Invalid quantity.") from None

        if quantity <= 0:
            raise ValidationError("Quantity must be greater than zero.")

        if service.unit == CatalogService.Unit.FIXED and quantity != Decimal("1.00"):
            raise ValidationError("Fixed-price services must use a quantity of 1.")

        return quantity

    def price_service(self, service: CatalogService, raw_quantity) -> PriceQuote:
        quantity = self.normalize_quantity(service, raw_quantity)
        unit_price = service.base_price.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        line_total = (quantity * unit_price).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return PriceQuote(
            service=service,
            quantity=quantity,
            unit_price=unit_price,
            line_total=line_total,
        )
