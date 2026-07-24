from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms

from apps.customers.models import Customer, CustomerBillingProfile


class StaffCustomerAccountForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = (
            "name",
            "billing_email",
            "siren",
            "vat_number",
            "is_active",
            "b2b_order_projects_enabled",
            "preferred_settlement_method",
            "default_shipping_mode",
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
            "notes",
        )
        labels = {
            "name": "Raison sociale",
            "billing_email": "E-mail de facturation",
            "siren": "SIREN",
            "vat_number": "N° TVA",
            "is_active": "Compte actif",
            "b2b_order_projects_enabled": "Projets B2B activés",
            "preferred_settlement_method": "Mode de règlement",
            "default_shipping_mode": "Acheminement par défaut",
            "notes": "Notes internes",
        }
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3, "class": "ui-input"}),
            "name": forms.TextInput(attrs={"class": "ui-input"}),
            "billing_email": forms.EmailInput(attrs={"class": "ui-input"}),
            "siren": forms.TextInput(attrs={"class": "ui-input"}),
            "vat_number": forms.TextInput(attrs={"class": "ui-input"}),
            "preferred_settlement_method": forms.Select(attrs={"class": "ui-input"}),
            "default_shipping_mode": forms.Select(attrs={"class": "ui-input"}),
            "billing_address_line1": forms.TextInput(attrs={"class": "ui-input"}),
            "billing_address_line2": forms.TextInput(attrs={"class": "ui-input"}),
            "billing_postal_code": forms.TextInput(attrs={"class": "ui-input"}),
            "billing_city": forms.TextInput(attrs={"class": "ui-input"}),
            "billing_country": forms.TextInput(attrs={"class": "ui-input"}),
            "shipping_address_line1": forms.TextInput(attrs={"class": "ui-input"}),
            "shipping_address_line2": forms.TextInput(attrs={"class": "ui-input"}),
            "shipping_postal_code": forms.TextInput(attrs={"class": "ui-input"}),
            "shipping_city": forms.TextInput(attrs={"class": "ui-input"}),
            "shipping_country": forms.TextInput(attrs={"class": "ui-input"}),
        }


class StaffCustomerPricingForm(forms.Form):
    negotiated_file_preparation_fee_eur = forms.DecimalField(
        label="Forfait préparation fichier (EUR / fichier)",
        required=False,
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
        help_text="Vide = tarif catalogue « Préparation fichier ».",
    )
    price_per_sqm_eur = forms.DecimalField(
        label="Prix DTF au m² négocié (EUR)",
        required=False,
        min_value=Decimal("0.00"),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
        help_text="Vide = prix catalogue DTF. Utilisé pour la tarification différée.",
    )
    billing_cycle = forms.ChoiceField(
        label="Cycle de facturation",
        choices=CustomerBillingProfile.BillingCycle.choices,
        initial=CustomerBillingProfile.BillingCycle.MONTHLY,
        widget=forms.Select(attrs={"class": "ui-input"}),
    )
    credit_limit_eur = forms.DecimalField(
        label="Plafond d’encours (EUR)",
        required=False,
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "ui-input", "step": "0.01", "min": "0"}),
        help_text="Optionnel. Vide = pas de plafond.",
    )
    enforce_credit_block = forms.BooleanField(
        label="Bloquer les commandes en dépassement d’encours",
        required=False,
        help_text="Sinon : simple avertissement sur la commande tarifée.",
    )

    @classmethod
    def from_customer(cls, customer: Customer) -> StaffCustomerPricingForm:
        profile = getattr(customer, "billing_profile", None)
        initial = {
            "negotiated_file_preparation_fee_eur": customer.negotiated_file_preparation_fee_eur,
            "price_per_sqm_eur": getattr(profile, "price_per_sqm_eur", None),
            "billing_cycle": getattr(
                profile,
                "billing_cycle",
                CustomerBillingProfile.BillingCycle.MONTHLY,
            ),
            "credit_limit_eur": getattr(profile, "credit_limit_eur", None),
            "enforce_credit_block": getattr(profile, "enforce_credit_block", False),
        }
        return cls(initial=initial)

    def clean_negotiated_file_preparation_fee_eur(self):
        return self._optional_money("negotiated_file_preparation_fee_eur")

    def clean_price_per_sqm_eur(self):
        return self._optional_money("price_per_sqm_eur")

    def clean_credit_limit_eur(self):
        return self._optional_money("credit_limit_eur")

    def _optional_money(self, field_name: str):
        raw = self.cleaned_data.get(field_name)
        if raw in (None, ""):
            return None
        try:
            value = Decimal(raw).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError) as exc:
            raise forms.ValidationError("Montant invalide.") from exc
        if value < 0:
            raise forms.ValidationError("Le montant ne peut pas être négatif.")
        return value
