from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from apps.customers.models import Customer
from apps.orders.services.external_orders import ExternalOrderService
from apps.shipping.services.methods import ShippingMethodService


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
    shipping_method_code = forms.ChoiceField(
        label="Mode de livraison",
        choices=[],
        help_text="Retrait, standard ou express — comme sur une commande classique.",
    )
    meterage_linear_m = forms.DecimalField(
        label="Métrage total (mètres linéaires)",
        required=False,
        min_value=Decimal("0.0001"),
        max_digits=12,
        decimal_places=4,
        widget=forms.NumberInput(attrs={"step": "0.0001", "min": "0.0001"}),
        help_text=(
            "Facultatif à la création. Sinon renseignez-le ensuite dans Pilotage "
            "ou sur la fiche commande (onglet Production)."
        ),
    )
    external_visual_count = forms.IntegerField(
        label="Nombre de visuels",
        min_value=1,
        max_value=10000,
        initial=1,
        help_text="Visuels distincts dans le lien, pour calculer les frais de préparation.",
    )
    support_color_hex = forms.CharField(
        label="Couleur du support",
        required=False,
        max_length=11,
        initial="#ffffff",
        help_text="Indicatif pour l’atelier, comme sur une commande par fichier.",
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    support_color_multicolor = forms.BooleanField(
        label="Support multicolore",
        required=False,
        help_text="Cochez si plusieurs couleurs de support (à la place d’une teinte unique).",
    )
    field_order = [
        "customer",
        "name",
        "external_url",
        "shipping_method_code",
        "external_visual_count",
        "support_color_hex",
        "support_color_multicolor",
        "meterage_linear_m",
        "customer_note",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True).order_by("name")
        shipping = ShippingMethodService()
        shipping.ensure_default_methods()
        methods = shipping.list_active_methods()
        self.fields["shipping_method_code"].choices = [
            (method.code, method.name) for method in methods
        ]
        if methods and not self.is_bound:
            default_code = next(
                (method.code for method in methods if method.is_pickup),
                methods[0].code,
            )
            self.fields["shipping_method_code"].initial = default_code
        # Checkbox : pas la classe ui-input pleine largeur.
        self.fields["support_color_multicolor"].widget.attrs.pop("class", None)
        self.fields["support_color_hex"].widget.attrs["class"] = (
            "h-10 w-14 cursor-pointer rounded-[var(--radius-sm)] "
            "border border-[color-mix(in_srgb,var(--line)_80%,transparent)] p-1"
        )

    def clean(self):
        cleaned = super().clean()
        customer = cleaned.get("customer")
        code = cleaned.get("shipping_method_code")
        if customer is not None:
            method = ShippingMethodService().resolve_method_for_customer(
                customer=customer,
                shipping_method_code=code or None,
            )
            cleaned["shipping_method_code"] = method.code
        if cleaned.get("support_color_multicolor"):
            cleaned["support_color_hex"] = "#multicolor"
        else:
            from apps.uploads.services.uploads import OrderUploadService

            try:
                cleaned["support_color_hex"] = OrderUploadService()._normalize_support_color(
                    cleaned.get("support_color_hex") or ""
                )
            except ValidationError as error:
                self.add_error("support_color_hex", error)
        cleaned.pop("support_color_multicolor", None)
        return cleaned
