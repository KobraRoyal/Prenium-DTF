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
            self.fields[            f"{prefix}__markup_percent"] = forms.DecimalField(
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
        default_count = sum(1 for payload in payloads if payload["is_default"] and payload["is_active"])
        if default_count != 1:
            raise forms.ValidationError(
                "Exactement une option active doit être définie comme option par défaut."
            )
        return cleaned
