from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.customers.models import Customer
from apps.customers.services.volume_discounts import (
    application_scope_for_customer,
    customer_has_personalized_ladder,
    resolve_active_ladder,
)
from apps.orders.services.pricing import OrderPricingService

TWOPLACES = Decimal("0.01")
DEFAULT_ROLL_WIDTH_MM = Decimal("550.00")


@dataclass(frozen=True)
class CustomerPricingRate:
    label: str
    detail: str
    amount: Decimal
    unit_label: str
    is_personalized: bool

    @property
    def source_label(self) -> str:
        return "Tarif personnalisé" if self.is_personalized else "Tarif catalogue par défaut"


@dataclass(frozen=True)
class CustomerVolumeDiscountTierPresentation:
    minimum_monthly_linear_m: Decimal
    discount_percent: Decimal
    meter_price_eur: Decimal
    threshold_label: str
    discount_label: str


@dataclass(frozen=True)
class CustomerPricingOverview:
    dtf_rate: CustomerPricingRate
    file_preparation_rate: CustomerPricingRate
    volume_discount_tiers: tuple[CustomerVolumeDiscountTierPresentation, ...]
    uses_personalized_volume_discount: bool
    volume_discount_application_scope: str
    laize_label: str
    meter_price_eur: Decimal

    @property
    def rates(self) -> tuple[CustomerPricingRate, CustomerPricingRate]:
        return (self.dtf_rate, self.file_preparation_rate)

    @property
    def volume_discount_source_label(self) -> str:
        if self.uses_personalized_volume_discount:
            return "Grille personnalisée"
        return "Grille par défaut"


class CustomerPricingOverviewService:
    """Présentation client des conditions réellement résolues par le moteur tarifaire."""

    def __init__(self, *, pricing: OrderPricingService | None = None):
        self.pricing = pricing or OrderPricingService()

    def present(self, *, customer: Customer) -> CustomerPricingOverview:
        billing_profile = getattr(customer, "billing_profile", None)
        has_personalized_dtf_rate = (
            billing_profile is not None and billing_profile.price_per_sqm_eur is not None
        )
        has_personalized_file_preparation_rate = (
            customer.negotiated_file_preparation_fee_eur is not None
        )
        uses_personalized_volume_discount = customer_has_personalized_ladder(customer)
        roll_width_mm = self._atelier_roll_width_mm()
        meter_price = self._price_for_one_meter(
            unit_price_per_sqm=self.pricing.resolve_unit_price_per_sqm(customer=customer),
            roll_width_mm=roll_width_mm,
        )
        ladder = resolve_active_ladder(customer)

        return CustomerPricingOverview(
            dtf_rate=CustomerPricingRate(
                label="Impression DTF",
                detail=f"1 mètre, laize {self._laize_label(roll_width_mm)}",
                amount=meter_price,
                unit_label="€ HT",
                is_personalized=has_personalized_dtf_rate,
            ),
            file_preparation_rate=CustomerPricingRate(
                label="Préparation de fichier",
                detail="Par fichier traité",
                amount=self.pricing.resolve_file_preparation_fee_per_file(customer=customer),
                unit_label="€ HT",
                is_personalized=has_personalized_file_preparation_rate,
            ),
            volume_discount_tiers=tuple(
                CustomerVolumeDiscountTierPresentation(
                    minimum_monthly_linear_m=tier.minimum_monthly_linear_m,
                    discount_percent=tier.discount_percent,
                    meter_price_eur=self._discounted_meter_price(
                        meter_price,
                        tier.discount_percent,
                    ),
                    threshold_label=self._plain_amount(tier.minimum_monthly_linear_m),
                    discount_label=self._plain_amount(tier.discount_percent),
                )
                for tier in ladder
            ),
            uses_personalized_volume_discount=uses_personalized_volume_discount,
            volume_discount_application_scope=application_scope_for_customer(customer),
            laize_label=self._laize_label(roll_width_mm),
            meter_price_eur=meter_price,
        )

    def _atelier_roll_width_mm(self) -> Decimal:
        from apps.gang_sheets.models import GangSheetSiteSettings

        row = GangSheetSiteSettings.objects.filter(singleton=True).only("roll_width_mm").first()
        if row is None or row.roll_width_mm is None:
            return DEFAULT_ROLL_WIDTH_MM
        return row.roll_width_mm

    def _laize_label(self, roll_width_mm: Decimal) -> str:
        centimeters = (roll_width_mm / Decimal("10")).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
        text = format(centimeters, "f").rstrip("0").rstrip(".")
        return f"{text.replace('.', ',')} cm"

    def _price_for_one_meter(
        self,
        *,
        unit_price_per_sqm: Decimal,
        roll_width_mm: Decimal,
    ) -> Decimal:
        laize_m = roll_width_mm / Decimal("1000")
        return (unit_price_per_sqm * laize_m).quantize(TWOPLACES, rounding=ROUND_HALF_UP)

    def _plain_amount(self, value: Decimal) -> str:
        text = format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
        return text.rstrip("0").rstrip(".").replace(".", ",")

    def _discounted_meter_price(self, meter_price: Decimal, discount_percent: Decimal) -> Decimal:
        factor = (Decimal("100.00") - discount_percent) / Decimal("100.00")
        return (meter_price * factor).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
