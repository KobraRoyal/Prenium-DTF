from decimal import Decimal

from django import forms

from apps.customers.models import Customer
from apps.orders.services.external_orders import ExternalOrderService


class ExternalOrderForm(forms.Form):
    name = forms.CharField(label="Nom de la commande", max_length=255)
    external_url = forms.URLField(
        assume_scheme="https",
        label="Lien de téléchargement du client",
        max_length=2000,
        help_text=(
            "Lien accessible à l’atelier (WeTransfer, Drive…). Vérifiez sa durée de validité."
        ),
    )
    customer_note = forms.CharField(
        label="Consignes pour l’atelier",
        required=False,
        max_length=5000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "external_%s")
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "ui-input w-full"

    def clean_external_url(self):
        return ExternalOrderService.validate_external_url(self.cleaned_data["external_url"])


class ProjectExternalOrderForm(ExternalOrderForm):
    """Map the shared order information to the external-link request."""

    requested_date = forms.DateField(required=False)

    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()
            data["customer_note"] = data.get("customer_comment", "")
        super().__init__(data, *args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        requested_date = cleaned.pop("requested_date", None)
        if requested_date:
            note = cleaned.get("customer_note", "")
            cleaned["customer_note"] = (
                f"Date souhaitée : {requested_date:%d/%m/%Y}\n{note}"
            ).strip()
        return cleaned


class StaffExternalOrderForm(ExternalOrderForm):
    customer = forms.ModelChoiceField(
        label="Client",
        queryset=Customer.objects.none(),
        to_field_name="public_id",
        empty_label="Choisir un client",
    )
    meterage_linear_m = forms.DecimalField(
        label="Métrage total (mètres linéaires)",
        min_value=Decimal("0.0001"),
        max_digits=12,
        decimal_places=4,
        widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0.0001"}),
        help_text="Métrage total à produire, toutes les copies comprises.",
    )
    external_visual_count = forms.IntegerField(
        label="Nombre de visuels",
        min_value=1,
        max_value=10000,
        initial=1,
        help_text="Visuels distincts dans le lien, pour calculer les frais de préparation.",
    )
    field_order = [
        "customer",
        "name",
        "external_url",
        "external_visual_count",
        "meterage_linear_m",
        "customer_note",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True).order_by("name")
