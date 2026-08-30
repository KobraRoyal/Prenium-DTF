from __future__ import annotations

from decimal import Decimal

from django import forms

from apps.catalog.services.default_pricing import DefaultCatalogPricingService
from apps.shipping.models import ShippingMethod


class StaffDefaultCatalogPricingForm(forms.Form):
    dtf_price_per_sqm_eur = forms.DecimalField(
        label="Prix DTF au m² (EUR)",
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
    )
    file_preparation_fee_eur = forms.DecimalField(
        label="Forfait préparation fichier (EUR / fichier)",
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
    )

    def __init__(self, *args, shipping_methods: tuple[ShippingMethod, ...] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        for method in shipping_methods or ():
            field_name = DefaultCatalogPricingService.shipping_field_name(method.code)
            if method.is_pickup:
                self.fields[field_name] = forms.DecimalField(
                    label=method.name,
                    min_value=Decimal("0.00"),
                    max_digits=10,
                    decimal_places=2,
                    initial=Decimal("0.00"),
                    disabled=True,
                    required=False,
                    widget=forms.NumberInput(
                        attrs={
                            "class": "ui-input",
                            "step": "0.01",
                            "min": "0",
                            "readonly": "readonly",
                        }
                    ),
                )
                continue
            self.fields[field_name] = forms.DecimalField(
                label=method.name,
                min_value=Decimal("0.00"),
                max_digits=10,
                decimal_places=2,
                widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
            )

    def shipping_prices(self) -> dict[str, Decimal]:
        prices: dict[str, Decimal] = {}
        for name, value in self.cleaned_data.items():
            if not name.startswith("shipping_price_"):
                continue
            prices[name.removeprefix("shipping_price_")] = value
        return prices
