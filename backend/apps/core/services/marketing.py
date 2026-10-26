"""Public, read-only offer. Never resolve a customer's negotiated prices here."""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.customers.models import DefaultCustomerVolumeDiscountTier
from apps.gang_sheets.models import GangSheetSiteSettings
from apps.orders.services.pricing import OrderPricingService


class PublicDtfOfferService:
    # Must match the clamp in static_src/js/dtf-pricing.js.
    VOLUME_MAX_M = 500
    RANGE_MIN_M = 50

    def snapshot(self) -> dict:
        width_cm = int(settings.DTF_LAIZE_CM)
        sheet = GangSheetSiteSettings.objects.first()
        offer = {
            "width_cm": width_cm,
            "sheet_width_cm": sheet.roll_width_mm / 10 if sheet else Decimal("55"),
            "sheet_max_cm": sheet.maximum_height_mm / 10 if sheet else Decimal("200"),
            "pricing": None,
            "tiers": [],
        }
        try:
            service = OrderPricingService().get_default_dtf_service(bootstrap=False)
        except ValidationError:
            return offer
        if width_cm <= 0 or service.currency != "EUR":
            return offer
        tiers = list(
            DefaultCustomerVolumeDiscountTier.objects.active()
            .order_by("minimum_monthly_linear_m")
            .values("minimum_monthly_linear_m", "discount_percent")
        )
        offer["tiers"] = tiers
        last_tier_m = int(tiers[-1]["minimum_monthly_linear_m"]) if tiers else 0
        offer["range_max_m"] = min(self.VOLUME_MAX_M, max(self.RANGE_MIN_M, last_tier_m * 2))
        offer["price_per_m"] = (service.base_price * Decimal(width_cm) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        offer["pricing"] = {
            "pricePerSqmCents": int(service.base_price * 100),
            "widthCm": width_cm,
            "tiers": [
                {
                    "minimum": str(row["minimum_monthly_linear_m"]),
                    "percent": str(row["discount_percent"]),
                }
                for row in tiers
            ],
        }
        return offer
