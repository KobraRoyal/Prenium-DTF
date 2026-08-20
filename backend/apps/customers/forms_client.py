from __future__ import annotations

from django import forms

from apps.customers.models import Customer
from apps.customers.services.company_profile import (
    COUNTRY_LABELS,
    compact_vat,
    digits_only,
    shipping_same_as_billing,
)

COUNTRY_CHOICES = tuple(COUNTRY_LABELS.items())


class ClientCompanyProfileForm(forms.ModelForm):
    billing_country = forms.ChoiceField(label="Pays de facturation", choices=COUNTRY_CHOICES)
    shipping_country = forms.ChoiceField(
        label="Pays de livraison",
        choices=COUNTRY_CHOICES,
        required=False,
    )
    shipping_same_as_billing = forms.BooleanField(
        label="Même adresse de livraison",
        required=False,
    )

    class Meta:
        model = Customer
        fields = (
            "name",
            "billing_email",
            "siren",
            "vat_number",
            "billing_address_line1",
            "billing_address_line2",
            "billing_postal_code",
            "billing_city",
            "billing_country",
            "shipping_address_line1",
            "shipping_address_line2",
            "shipping_postal_code",
            "shipping_city",
            "shipping_country",
        )
        labels = {
            "name": "Raison sociale",
            "billing_email": "E-mail de facturation",
            "siren": "SIREN",
            "vat_number": "N° TVA",
            "billing_address_line1": "Adresse",
            "billing_address_line2": "Complément",
            "billing_postal_code": "Code postal",
            "billing_city": "Ville",
            "shipping_address_line1": "Adresse",
            "shipping_address_line2": "Complément",
            "shipping_postal_code": "Code postal",
            "shipping_city": "Ville",
        }
        widgets = {
            "name": forms.TextInput(attrs={"class": "ui-input", "autocomplete": "organization"}),
            "billing_email": forms.EmailInput(attrs={"class": "ui-input", "autocomplete": "email"}),
            "siren": forms.TextInput(
                attrs={"class": "ui-input", "inputmode": "numeric", "autocomplete": "off"}
            ),
            "vat_number": forms.TextInput(attrs={"class": "ui-input", "autocomplete": "off"}),
            "billing_address_line1": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "address-line1"}
            ),
            "billing_address_line2": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "address-line2"}
            ),
            "billing_postal_code": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "postal-code"}
            ),
            "billing_city": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "address-level2"}
            ),
            "shipping_address_line1": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "shipping address-line1"}
            ),
            "shipping_address_line2": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "shipping address-line2"}
            ),
            "shipping_postal_code": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "shipping postal-code"}
            ),
            "shipping_city": forms.TextInput(
                attrs={"class": "ui-input", "autocomplete": "shipping address-level2"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["billing_email"].required = False
        self.fields["siren"].required = False
        self.fields["vat_number"].required = False
        current_billing = (getattr(self.instance, "billing_country", "") or "FR").upper()
        current_shipping = (getattr(self.instance, "shipping_country", "") or "FR").upper()
        self.fields["billing_country"].choices = _choices_with_current(current_billing)
        self.fields["shipping_country"].choices = _choices_with_current(current_shipping)
        if not self.is_bound:
            self.fields["shipping_same_as_billing"].initial = shipping_same_as_billing(
                self.instance
            )

    def clean_siren(self) -> str:
        return digits_only(self.cleaned_data.get("siren", ""))[:9]

    def clean_vat_number(self) -> str:
        return compact_vat(self.cleaned_data.get("vat_number", ""))[:32]

    def clean_billing_country(self) -> str:
        return (self.cleaned_data.get("billing_country") or "FR").strip().upper()[:2]

    def clean_shipping_country(self) -> str:
        return (self.cleaned_data.get("shipping_country") or "").strip().upper()[:2]

    def clean(self):
        data = super().clean()
        country = data.get("billing_country") or "FR"
        siren = data.get("siren") or ""
        vat_number = data.get("vat_number") or ""
        if country == "FR" and siren and len(siren) != 9:
            self.add_error("siren", "Saisissez les 9 chiffres du numéro SIREN.")
        if vat_number and len(vat_number) < 4:
            self.add_error("vat_number", "Saisissez un numéro de TVA valide.")
        if data.get("shipping_same_as_billing"):
            data["shipping_address_line1"] = data.get("billing_address_line1") or ""
            data["shipping_address_line2"] = data.get("billing_address_line2") or ""
            data["shipping_postal_code"] = data.get("billing_postal_code") or ""
            data["shipping_city"] = data.get("billing_city") or ""
            data["shipping_country"] = data.get("billing_country") or "FR"
        elif not data.get("shipping_country"):
            data["shipping_country"] = data.get("billing_country") or "FR"
        return data


def _choices_with_current(current: str) -> list[tuple[str, str]]:
    choices = list(COUNTRY_CHOICES)
    codes = {code for code, _label in choices}
    if current and current not in codes:
        choices.append((current, COUNTRY_LABELS.get(current, current)))
    return choices
