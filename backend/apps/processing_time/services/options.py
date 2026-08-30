from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from django.core.exceptions import ValidationError

from apps.processing_time.models import ZERO_AMOUNT, ProcessingTimeOption
from apps.processing_time.services.customer_overrides import (
    CustomerProcessingTimeOverrideService,
    ResolvedProcessingTimeOption,
)

TWOPLACES = Decimal("0.01")

DEFAULT_OPTION_SEED = (
    {
        "code": "standard",
        "name": "Standard",
        "eta_label": "Imprimé et expédié dans 3 jours",
        "disclaimer": "Hors weekend et jour férié",
        "business_days": 3,
        "markup_percent": Decimal("0.00"),
        "flat_fee_eur": Decimal("0.00"),
        "is_default": True,
        "display_order": 10,
    },
    {
        "code": "fast",
        "name": "Rapide",
        "eta_label": "Imprimé et expédié dans 2 jours",
        "disclaimer": "Hors weekend et jour férié",
        "business_days": 2,
        "markup_percent": Decimal("20.00"),
        "flat_fee_eur": Decimal("0.00"),
        "is_default": False,
        "display_order": 20,
    },
    {
        "code": "express",
        "name": "Express",
        "eta_label": "Imprimé et expédié demain",
        "disclaimer": "Hors weekend et jour férié",
        "business_days": 0,
        "markup_percent": Decimal("40.00"),
        "flat_fee_eur": Decimal("7.00"),
        "is_default": False,
        "display_order": 30,
    },
)


class _PricingOption(Protocol):
    code: str
    name: str
    eta_label: str
    markup_percent: Decimal
    flat_fee_eur: Decimal


class ProcessingTimeOptionService:
    """Catalogue et résolution des options de délai de traitement."""

    def __init__(self, *, customer_overrides: CustomerProcessingTimeOverrideService | None = None):
        self.customer_overrides = customer_overrides or CustomerProcessingTimeOverrideService()

    def list_active_options(self):
        return list(ProcessingTimeOption.objects.active().order_by("display_order", "name"))

    def list_active_options_for_customer(self, customer) -> list[ResolvedProcessingTimeOption]:
        self.ensure_default_options()
        return self.customer_overrides.list_resolved_for_customer(customer)

    def ensure_default_options(self) -> list[ProcessingTimeOption]:
        created: list[ProcessingTimeOption] = []
        for payload in DEFAULT_OPTION_SEED:
            option, was_created = ProcessingTimeOption.objects.get_or_create(
                code=payload["code"],
                defaults={
                    "name": payload["name"],
                    "eta_label": payload["eta_label"],
                    "disclaimer": payload["disclaimer"],
                    "business_days": payload["business_days"],
                    "markup_percent": payload["markup_percent"],
                    "flat_fee_eur": payload["flat_fee_eur"],
                    "is_default": payload["is_default"],
                    "display_order": payload["display_order"],
                    "is_active": True,
                },
            )
            if was_created:
                created.append(option)
        return created

    def get_active_by_code(self, code: str | None) -> ProcessingTimeOption | None:
        normalized = str(code or "").strip().lower()
        if not normalized:
            return None
        return ProcessingTimeOption.objects.active().filter(code=normalized).first()

    def require_active_by_code(self, code: str | None) -> ProcessingTimeOption:
        option = self.get_active_by_code(code)
        if option is None:
            raise ValidationError("Choisissez un délai de traitement valide.")
        return option

    def resolve_default_code(self, *, customer=None) -> str:
        self.ensure_default_options()
        if customer is not None:
            options = self.list_active_options_for_customer(customer)
            if not options:
                raise ValidationError("Aucune option de délai active pour ce client.")
            default = next((option for option in options if option.is_default), None)
            return (default or options[0]).code
        default = (
            ProcessingTimeOption.objects.active().filter(is_default=True).order_by("display_order").first()
        )
        if default is not None:
            return default.code
        fallback = ProcessingTimeOption.objects.active().order_by("display_order").first()
        if fallback is None:
            raise ValidationError("Aucune option de délai de traitement active.")
        return fallback.code

    def resolve_option(
        self,
        *,
        processing_time_code: str | None = None,
        order=None,
        customer=None,
    ) -> _PricingOption:
        self.ensure_default_options()
        if customer is not None:
            return self.resolve_option_for_customer(
                customer=customer,
                processing_time_code=processing_time_code,
                order=order,
            )
        if processing_time_code:
            return self.require_active_by_code(processing_time_code)
        if order is not None and getattr(order, "processing_time_code", ""):
            existing = self.get_active_by_code(order.processing_time_code)
            if existing is not None:
                return existing
        return self.require_active_by_code(self.resolve_default_code())

    def resolve_option_for_customer(
        self,
        *,
        customer,
        processing_time_code: str | None = None,
        order=None,
    ) -> ResolvedProcessingTimeOption:
        self.ensure_default_options()
        code = processing_time_code
        if not code and order is not None and getattr(order, "processing_time_code", ""):
            code = order.processing_time_code
        if not code:
            code = self.resolve_default_code(customer=customer)
        global_option = self.require_active_by_code(code)
        resolved = self.customer_overrides.resolve_for_customer(
            customer=customer,
            option=global_option,
        )
        if not resolved.is_enabled:
            enabled = self.list_active_options_for_customer(customer)
            if not enabled:
                raise ValidationError("Aucune option de délai active pour ce client.")
            fallback = next((option for option in enabled if option.is_default), enabled[0])
            if fallback.code == resolved.code:
                raise ValidationError("Aucune option de délai active pour ce client.")
            return fallback
        return resolved

    def snapshot_dict(self, option: _PricingOption) -> dict[str, object]:
        markup_percent = (option.markup_percent or ZERO_AMOUNT).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
        flat_fee = (option.flat_fee_eur or ZERO_AMOUNT).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
        return {
            "processing_time_code": option.code,
            "processing_time_name": option.name,
            "processing_time_eta_label": option.eta_label,
            "processing_time_markup_percent": markup_percent,
            "processing_time_flat_fee": flat_fee,
        }

    def apply_snapshot_to_order(self, *, order, option: _PricingOption) -> None:
        snap = self.snapshot_dict(option)
        order.processing_time_code = str(snap["processing_time_code"])
        order.processing_time_name = str(snap["processing_time_name"])
        order.processing_time_markup_percent = snap["processing_time_markup_percent"]  # type: ignore[assignment]
        order.processing_time_flat_fee = snap["processing_time_flat_fee"]  # type: ignore[assignment]
        order.processing_time_markup_amount = ZERO_AMOUNT
        order.processing_time_surcharge_amount = ZERO_AMOUNT

    def compute_surcharge(
        self,
        *,
        dtf_amount: Decimal,
        option: _PricingOption | None = None,
        markup_percent: Decimal | None = None,
        flat_fee: Decimal | None = None,
    ) -> dict[str, Decimal]:
        """Calcule la majoration délai sur le montant DTF (après remise volume)."""
        if option is not None:
            percent = option.markup_percent or ZERO_AMOUNT
            fee = option.flat_fee_eur or ZERO_AMOUNT
        else:
            percent = markup_percent or ZERO_AMOUNT
            fee = flat_fee or ZERO_AMOUNT
        percent = percent.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        fee = fee.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        dtf_base = dtf_amount.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        markup_amount = (dtf_base * percent / Decimal("100.00")).quantize(
            TWOPLACES,
            rounding=ROUND_HALF_UP,
        )
        surcharge = (markup_amount + fee).quantize(TWOPLACES, rounding=ROUND_HALF_UP)
        return {
            "processing_time_markup_percent": percent,
            "processing_time_markup_amount": markup_amount,
            "processing_time_flat_fee": fee,
            "processing_time_surcharge_amount": surcharge,
        }

    def surcharge_from_order_snapshot(self, *, order, dtf_amount: Decimal) -> dict[str, Decimal]:
        code = str(getattr(order, "processing_time_code", "") or "").strip()
        if not code:
            return {
                "processing_time_markup_percent": ZERO_AMOUNT,
                "processing_time_markup_amount": ZERO_AMOUNT,
                "processing_time_flat_fee": ZERO_AMOUNT,
                "processing_time_surcharge_amount": ZERO_AMOUNT,
            }
        if getattr(order, "customer_id", None):
            global_option = self.get_active_by_code(code)
            if global_option is not None:
                resolved = self.customer_overrides.resolve_for_customer(
                    customer=order.customer,
                    option=global_option,
                )
                return self.compute_surcharge(dtf_amount=dtf_amount, option=resolved)
        return self.compute_surcharge(
            dtf_amount=dtf_amount,
            markup_percent=getattr(order, "processing_time_markup_percent", ZERO_AMOUNT) or ZERO_AMOUNT,
            flat_fee=getattr(order, "processing_time_flat_fee", ZERO_AMOUNT) or ZERO_AMOUNT,
        )

    def checkout_ui_context(
        self,
        *,
        customer=None,
        order=None,
        widget: str = "radios",
    ) -> dict:
        self.ensure_default_options()
        if customer is not None:
            options = self.list_active_options_for_customer(customer)
        else:
            options = self.list_active_options()
        if not options:
            return {
                "processing_time_options": [],
                "selected_processing_time_code": "",
                "show_processing_time_choice": False,
                "processing_time_choice_widget": "hidden",
            }
        if order is not None and getattr(order, "processing_time_code", ""):
            selected = order.processing_time_code
        elif customer is not None:
            selected = self.resolve_default_code(customer=customer)
        else:
            selected = self.resolve_default_code()
        return {
            "processing_time_options": options,
            "selected_processing_time_code": selected,
            "show_processing_time_choice": True,
            "processing_time_choice_widget": widget,
        }
