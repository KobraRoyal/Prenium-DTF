from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.validators import MinValueValidator

from apps.processing_time.models import ProcessingTimeOption

TWOPLACES = Decimal("0.01")


class StaffProcessingTimeSettingsForm(forms.Form):
    """Formulaire agrégé : une option par ligne (identifiée par code)."""

    def __init__(self, *args, options: tuple[ProcessingTimeOption, ...] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.option_codes: list[str] = []
        for option in options or ():
            prefix = option.code.replace("-", "_")
            self.option_codes.append(option.code)
            self.fields[f"{prefix}__name"] = forms.CharField(
                label=f"{option.name} — libellé interne",
                max_length=255,
                initial=option.name,
            )
            self.fields[f"{prefix}__eta_label"] = forms.CharField(
                label="Texte délai client",
                max_length=255,
                initial=option.eta_label,
            )
            self.fields[f"{prefix}__disclaimer"] = forms.CharField(
                label="Mention légale",
                max_length=255,
                initial=option.disclaimer,
            )
            self.fields[f"{prefix}__business_days"] = forms.IntegerField(
                label="Jours ouvrés",
                min_value=0,
                initial=option.business_days,
            )
            self.fields[f"{prefix}__markup_percent"] = forms.DecimalField(
                label="Majoration % sur DTF uniquement",
                min_value=Decimal("0.00"),
                max_digits=5,
                decimal_places=2,
                initial=option.markup_percent,
                validators=[MinValueValidator(Decimal("0.00"))],
            )
            self.fields[f"{prefix}__flat_fee_eur"] = forms.DecimalField(
                label="Forfait HT (€)",
                min_value=Decimal("0.00"),
                max_digits=10,
                decimal_places=2,
                initial=option.flat_fee_eur,
                validators=[MinValueValidator(Decimal("0.00"))],
            )
            self.fields[f"{prefix}__is_default"] = forms.BooleanField(
                label="Option par défaut",
                required=False,
                initial=option.is_default,
            )
            self.fields[f"{prefix}__is_active"] = forms.BooleanField(
                label="Active",
                required=False,
                initial=option.is_active,
            )
            self.fields[f"{prefix}__display_order"] = forms.IntegerField(
                label="Ordre d'affichage",
                min_value=0,
                initial=option.display_order,
            )

    def cleaned_option_payloads(self) -> list[dict]:
        payloads: list[dict] = []
        for code in self.option_codes:
            prefix = code.replace("-", "_")
            payloads.append(
                {
                    "code": code,
                    "name": self.cleaned_data[f"{prefix}__name"].strip(),
                    "eta_label": self.cleaned_data[f"{prefix}__eta_label"].strip(),
                    "disclaimer": self.cleaned_data[f"{prefix}__disclaimer"].strip(),
                    "business_days": self.cleaned_data[f"{prefix}__business_days"],
                    "markup_percent": self.cleaned_data[f"{prefix}__markup_percent"],
                    "flat_fee_eur": self.cleaned_data[f"{prefix}__flat_fee_eur"],
                    "is_default": self.cleaned_data[f"{prefix}__is_default"],
                    "is_active": self.cleaned_data[f"{prefix}__is_active"],
                    "display_order": self.cleaned_data[f"{prefix}__display_order"],
                }
            )
        return payloads

    def clean(self):
        cleaned = super().clean()
        if cleaned is None:
            return cleaned
        payloads = self.cleaned_option_payloads()
        default_count = sum(
            1 for payload in payloads if payload["is_default"] and payload["is_active"]
        )
        if default_count != 1:
            raise forms.ValidationError(
                "Exactement une option active doit être définie comme option par défaut."
            )
        return cleaned


class StaffCustomerProcessingTimeOverridesForm(forms.Form):
    """Dérogations délai de traitement pour un compte client."""

    def __init__(self, *args, rows: list[dict] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.option_codes: list[str] = []
        for row in rows or ():
            option = row["option"]
            prefix = option.code.replace("-", "_")
            self.option_codes.append(option.code)
            self.fields[f"{prefix}__is_enabled"] = forms.BooleanField(
                label="Proposer au client",
                required=False,
                initial=row["is_enabled"],
            )
            self.fields[f"{prefix}__markup_percent"] = forms.DecimalField(
                label="Majoration % client",
                required=False,
                min_value=Decimal("0.00"),
                max_digits=5,
                decimal_places=2,
                initial=row["markup_percent"],
                validators=[MinValueValidator(Decimal("0.00"))],
                help_text=f"Défaut atelier : {option.markup_percent} %",
                widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
            )
            self.fields[f"{prefix}__flat_fee_eur"] = forms.DecimalField(
                label="Forfait HT client",
                required=False,
                min_value=Decimal("0.00"),
                max_digits=10,
                decimal_places=2,
                initial=row["flat_fee_eur"],
                validators=[MinValueValidator(Decimal("0.00"))],
                help_text=f"Défaut atelier : {option.flat_fee_eur} €",
                widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
            )

    @classmethod
    def from_customer(cls, customer):
        from apps.processing_time.services.customer_overrides import (
            CustomerProcessingTimeOverrideService,
        )

        rows = CustomerProcessingTimeOverrideService().rows_for_staff_form(customer)
        return cls(rows=rows)

    def cleaned_option_payloads(self) -> list[dict]:
        payloads: list[dict] = []
        for code in self.option_codes:
            prefix = code.replace("-", "_")
            markup = self.cleaned_data.get(f"{prefix}__markup_percent")
            flat_fee = self.cleaned_data.get(f"{prefix}__flat_fee_eur")
            payloads.append(
                {
                    "code": code,
                    "is_enabled": self.cleaned_data.get(f"{prefix}__is_enabled", True),
                    "markup_percent": markup,
                    "flat_fee_eur": flat_fee,
                }
            )
        return payloads

    def clean(self):
        cleaned = super().clean()
        if cleaned is None:
            return cleaned
        enabled_count = sum(
            1 for payload in self.cleaned_option_payloads() if payload["is_enabled"]
        )
        if enabled_count < 1:
            raise forms.ValidationError(
                "Au moins une option de délai doit rester proposée au client."
            )
        return cleaned
