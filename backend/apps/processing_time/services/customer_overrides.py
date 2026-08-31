from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.models import AbstractBaseUser
from django.db import transaction

from apps.auditlog.services import record_event
from apps.processing_time.models import (
    ZERO_AMOUNT,
    CustomerProcessingTimeOptionOverride,
    ProcessingTimeOption,
)

TWOPLACES = Decimal("0.01")


@dataclass(frozen=True)
class ResolvedProcessingTimeOption:
    """Option délai résolue pour un client (catalogue global + dérogation éventuelle)."""

    code: str
    name: str
    eta_label: str
    disclaimer: str
    business_days: int
    markup_percent: Decimal
    flat_fee_eur: Decimal
    is_default: bool
    display_order: int
    is_enabled: bool = True
    has_custom_pricing: bool = False

    @property
    def client_label(self) -> str:
        parts = [self.eta_label.strip()]
        if self.disclaimer.strip():
            parts.append(f"« {self.disclaimer.strip()} »")
        return " ".join(part for part in parts if part)


class CustomerProcessingTimeOverrideService:
    def override_map(self, customer) -> dict[int, CustomerProcessingTimeOptionOverride]:
        return {
            row.option_id: row
            for row in CustomerProcessingTimeOptionOverride.objects.filter(
                customer=customer
            ).select_related("option")
        }

    def merge(
        self,
        *,
        option: ProcessingTimeOption,
        override: CustomerProcessingTimeOptionOverride | None = None,
    ) -> ResolvedProcessingTimeOption:
        markup = option.markup_percent or ZERO_AMOUNT
        flat_fee = option.flat_fee_eur or ZERO_AMOUNT
        is_enabled = True
        has_custom = False
        if override is not None:
            is_enabled = bool(override.is_enabled)
            if override.markup_percent is not None:
                markup = override.markup_percent
                has_custom = True
            if override.flat_fee_eur is not None:
                flat_fee = override.flat_fee_eur
                has_custom = True
            if not override.is_enabled:
                has_custom = True
        return ResolvedProcessingTimeOption(
            code=option.code,
            name=option.name,
            eta_label=option.eta_label,
            disclaimer=option.disclaimer,
            business_days=option.business_days,
            markup_percent=markup.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
            flat_fee_eur=flat_fee.quantize(TWOPLACES, rounding=ROUND_HALF_UP),
            is_default=option.is_default,
            display_order=option.display_order,
            is_enabled=is_enabled,
            has_custom_pricing=has_custom,
        )

    def list_resolved_for_customer(self, customer) -> list[ResolvedProcessingTimeOption]:
        overrides = self.override_map(customer)
        resolved: list[ResolvedProcessingTimeOption] = []
        for option in ProcessingTimeOption.objects.active().order_by("display_order", "name"):
            merged = self.merge(option=option, override=overrides.get(option.pk))
            if merged.is_enabled:
                resolved.append(merged)
        return resolved

    def resolve_for_customer(
        self,
        *,
        customer,
        option: ProcessingTimeOption,
    ) -> ResolvedProcessingTimeOption:
        override = self.override_map(customer).get(option.pk)
        return self.merge(option=option, override=override)

    def customer_has_customizations(self, customer) -> bool:
        return CustomerProcessingTimeOptionOverride.objects.filter(customer=customer).exists()

    @transaction.atomic
    def update_for_customer(
        self,
        *,
        customer,
        payloads: list[dict],
        actor: AbstractBaseUser,
        source: str,
    ) -> list[CustomerProcessingTimeOptionOverride]:
        updated: list[CustomerProcessingTimeOptionOverride] = []
        options_by_code = {
            option.code: option
            for option in ProcessingTimeOption.objects.all().order_by("display_order")
        }
        for payload in payloads:
            option = options_by_code[payload["code"]]
            markup = payload.get("markup_percent")
            flat_fee = payload.get("flat_fee_eur")
            is_enabled = bool(payload.get("is_enabled", True))
            inherits_global = (
                is_enabled
                and markup is None
                and flat_fee is None
            )
            existing = (
                CustomerProcessingTimeOptionOverride.objects.select_for_update()
                .filter(customer=customer, option=option)
                .first()
            )
            if inherits_global:
                if existing is not None:
                    existing.delete()
                continue
            if existing is None:
                CustomerProcessingTimeOptionOverride.objects.create(
                    customer=customer,
                    option=option,
                    markup_percent=markup,
                    flat_fee_eur=flat_fee,
                    is_enabled=is_enabled,
                )
                updated.append(
                    CustomerProcessingTimeOptionOverride.objects.get(
                        customer=customer,
                        option=option,
                    )
                )
                continue
            existing.markup_percent = markup
            existing.flat_fee_eur = flat_fee
            existing.is_enabled = is_enabled
            existing.save(
                update_fields=[
                    "markup_percent",
                    "flat_fee_eur",
                    "is_enabled",
                    "updated_at",
                ]
            )
            updated.append(existing)
        record_event(
            action="customer.processing_time_overrides_updated",
            actor=actor,
            target=customer,
            metadata={
                "source": source,
                "customer_public_id": str(customer.public_id),
                "override_count": len(updated),
            },
        )
        return updated

    def rows_for_staff_form(self, customer) -> list[dict]:
        overrides = self.override_map(customer)
        rows: list[dict] = []
        for option in ProcessingTimeOption.objects.all().order_by("display_order", "name"):
            override = overrides.get(option.pk)
            rows.append(
                {
                    "option": option,
                    "override": override,
                    "is_enabled": override.is_enabled if override else True,
                    "markup_percent": override.markup_percent if override else None,
                    "flat_fee_eur": override.flat_fee_eur if override else None,
                }
            )
        return rows
