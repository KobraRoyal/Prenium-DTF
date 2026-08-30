from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.auditlog.services import record_event
from apps.catalog.models import CatalogService
from apps.catalog.services.default_catalog import DefaultCatalogService
from apps.orders.services.pricing import OrderPricingService
from apps.shipping.models import ShippingMethod
from apps.shipping.services.methods import ShippingMethodService

TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class ShippingMethodPricingRow:
    method: ShippingMethod
    base_price_eur: Decimal


@dataclass(frozen=True)
class DefaultCatalogPricingSnapshot:
    dtf_service: CatalogService
    file_preparation_service: CatalogService
    dtf_price_per_sqm_eur: Decimal
    file_preparation_fee_eur: Decimal
    shipping_methods: tuple[ShippingMethodPricingRow, ...]


class DefaultCatalogPricingService:
    def __init__(
        self,
        *,
        pricing: OrderPricingService | None = None,
        shipping_methods: ShippingMethodService | None = None,
        catalog_bootstrap: DefaultCatalogService | None = None,
    ):
        self.pricing = pricing or OrderPricingService()
        self.shipping_methods = shipping_methods or ShippingMethodService()
        self.catalog_bootstrap = catalog_bootstrap or DefaultCatalogService()

    def snapshot(self) -> DefaultCatalogPricingSnapshot:
        self.catalog_bootstrap.ensure_default_services()
        dtf_service = self.pricing.get_default_dtf_service()
        file_preparation_service = self.pricing.get_default_file_preparation_service()
        self.shipping_methods.ensure_default_methods()
        shipping_rows = tuple(
            ShippingMethodPricingRow(
                method=method,
                base_price_eur=method.resolved_price.quantize(
                    TWOPLACES,
                    rounding=ROUND_HALF_UP,
                ),
            )
            for method in self.shipping_methods.list_active_methods()
        )
        return DefaultCatalogPricingSnapshot(
            dtf_service=dtf_service,
            file_preparation_service=file_preparation_service,
            dtf_price_per_sqm_eur=dtf_service.base_price.quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            ),
            file_preparation_fee_eur=file_preparation_service.base_price.quantize(
                TWOPLACES,
                rounding=ROUND_HALF_UP,
            ),
            shipping_methods=shipping_rows,
        )

    @transaction.atomic
    def update(
        self,
        *,
        dtf_price_per_sqm_eur: Decimal,
        file_preparation_fee_eur: Decimal,
        shipping_prices: dict[str, Decimal],
        actor: AbstractBaseUser,
        source: str,
    ) -> DefaultCatalogPricingSnapshot:
        current = self.snapshot()
        dtf_price = dtf_price_per_sqm_eur.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        file_prep_price = file_preparation_fee_eur.quantize(TWOPLACES, rounding=ROUND_HALF_UP)

        dtf_service = current.dtf_service
        file_preparation_service = current.file_preparation_service
        dtf_service.base_price = dtf_price
        file_preparation_service.base_price = file_prep_price
        dtf_service.save(update_fields=["base_price", "updated_at"])
        file_preparation_service.save(update_fields=["base_price", "updated_at"])

        shipping_updates: dict[str, str] = {}
        for row in current.shipping_methods:
            method = row.method
            if method.is_pickup:
                method.base_price = Decimal("0.00")
            else:
                submitted = shipping_prices.get(method.code)
                if submitted is None:
                    continue
                method.base_price = submitted.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
            method.save(update_fields=["base_price", "updated_at"])
            shipping_updates[method.code] = str(method.resolved_price)

        record_event(
            action="catalog.default_pricing_updated",
            actor=actor,
            target=dtf_service,
            metadata={
                "source": source,
                "dtf_service_code": dtf_service.code,
                "file_preparation_service_code": file_preparation_service.code,
                "dtf_price_per_sqm_eur": str(dtf_price),
                "file_preparation_fee_eur": str(file_prep_price),
                "shipping_prices": shipping_updates,
            },
        )
        return self.snapshot()

    @staticmethod
    def shipping_field_name(code: str) -> str:
        return f"shipping_price_{code}"
