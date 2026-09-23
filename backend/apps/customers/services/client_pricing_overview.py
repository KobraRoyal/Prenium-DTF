from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.customers.models import Customer
from apps.customers.services.volume_discounts import (
    application_scope_for_customer,
    customer_has_personalized_ladder,
    resolve_active_ladder,
)
from apps.orders.services.pricing import OrderPricingService


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


@dataclass(frozen=True)
class CustomerPricingOverview:
    dtf_rate: CustomerPricingRate
    file_preparation_rate: CustomerPricingRate
    volume_discount_tiers: tuple[CustomerVolumeDiscountTierPresentation, ...]
    uses_personalized_volume_discount: bool
    volume_discount_application_scope: str

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

        return CustomerPricingOverview(
            dtf_rate=CustomerPricingRate(
                label="Impression DTF",
                detail="Par m² facturable",
                amount=self.pricing.resolve_unit_price_per_sqm(customer=customer),
                unit_label="€/m²",
                is_personalized=has_personalized_dtf_rate,
            ),
            file_preparation_rate=CustomerPricingRate(
                label="Préparation de fichier",
                detail="Par fichier traité",
                amount=self.pricing.resolve_file_preparation_fee_per_file(customer=customer),
                unit_label="€/fichier",
                is_personalized=has_personalized_file_preparation_rate,
            ),
            volume_discount_tiers=tuple(
                CustomerVolumeDiscountTierPresentation(
                    minimum_monthly_linear_m=tier.minimum_monthly_linear_m,
                    discount_percent=tier.discount_percent,
                )
                for tier in resolve_active_ladder(customer)
            ),
            uses_personalized_volume_discount=uses_personalized_volume_discount,
            volume_discount_application_scope=application_scope_for_customer(customer),
        )
