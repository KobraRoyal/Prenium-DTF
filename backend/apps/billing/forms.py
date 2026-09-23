from __future__ import annotations

from datetime import date, datetime, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.billing.services.gateway_settings import PaymentGatewaySnapshot


def previous_closed_month_start(*, today: date | None = None) -> date:
    current_month = (today or timezone.localdate()).replace(day=1)
    return (current_month - timedelta(days=1)).replace(day=1)


class BillingStatementMonthForm(forms.Form):
    month = forms.CharField(
        label="Mois à clôturer",
        widget=forms.TextInput(
            attrs={
                "type": "month",
                "class": "ui-input",
                "autocomplete": "off",
            }
        ),
    )

    def __init__(self, *args, today: date | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        latest_month = previous_closed_month_start(today=today)
        self.fields["month"].initial = latest_month.strftime("%Y-%m")
        self.fields["month"].widget.attrs["max"] = latest_month.strftime("%Y-%m")

    def clean_month(self) -> date:
        raw_month = str(self.cleaned_data.get("month") or "").strip()
        try:
            month_start = datetime.strptime(raw_month, "%Y-%m").date()
        except ValueError as exc:
            raise ValidationError("Sélectionnez un mois valide.") from exc

        current_month = timezone.localdate().replace(day=1)
        if month_start >= current_month:
            raise ValidationError("Le mois doit être clôturé avant de générer son récapitulatif.")
        return month_start


def _secret_input(*, autocomplete: str) -> forms.PasswordInput:
    return forms.PasswordInput(
        render_value=False,
        attrs={
            "class": "ui-input",
            "autocomplete": autocomplete,
            "spellcheck": "false",
        },
    )


def _text_input(*, placeholder: str = "") -> forms.TextInput:
    attrs = {
        "class": "ui-input",
        "autocomplete": "off",
        "spellcheck": "false",
    }
    if placeholder:
        attrs["placeholder"] = placeholder
    return forms.TextInput(attrs=attrs)


class PaymentGatewaySettingsForm(forms.Form):
    paypal_enabled = forms.BooleanField(
        required=False,
        label="Activer PayPal",
        widget=forms.CheckboxInput(attrs={"id": "id_paypal_enabled"}),
    )
    paypal_client_id = forms.CharField(
        required=False,
        label="Client ID PayPal",
        max_length=255,
        widget=_text_input(placeholder="AXxxxxxxxx"),
    )
    paypal_client_secret = forms.CharField(
        required=False,
        label="Secret PayPal",
        widget=_secret_input(autocomplete="new-password"),
    )
    paypal_webhook_id = forms.CharField(
        required=False,
        label="ID du webhook PayPal",
        max_length=255,
        widget=_text_input(),
    )
    stripe_enabled = forms.BooleanField(
        required=False,
        label="Activer Stripe",
        widget=forms.CheckboxInput(attrs={"id": "id_stripe_enabled"}),
    )
    stripe_publishable_key = forms.CharField(
        required=False,
        label="Clé publiable Stripe",
        max_length=255,
        widget=_text_input(placeholder="pk_live_… ou pk_test_…"),
    )
    stripe_secret_key = forms.CharField(
        required=False,
        label="Clé secrète Stripe",
        widget=_secret_input(autocomplete="new-password"),
    )
    stripe_webhook_secret = forms.CharField(
        required=False,
        label="Secret webhook Stripe",
        widget=_secret_input(autocomplete="new-password"),
    )

    def __init__(self, *args, snapshot: PaymentGatewaySnapshot, **kwargs):
        self.snapshot = snapshot
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            self.initial.update(
                {
                    "paypal_enabled": snapshot.paypal_enabled,
                    "stripe_enabled": snapshot.stripe_enabled,
                    "paypal_client_id": snapshot.paypal_client_id,
                    "paypal_webhook_id": snapshot.paypal_webhook_id,
                    "stripe_publishable_key": snapshot.stripe_publishable_key,
                }
            )
        self.fields["paypal_client_secret"].help_text = (
            f"Enregistré : {snapshot.paypal_secret_hint}. Laissez vide pour conserver."
            if snapshot.paypal_secret_hint
            else "Collez le secret Client PayPal. Il ne sera plus affiché ensuite."
        )
        self.fields["stripe_secret_key"].help_text = (
            f"Enregistrée : {snapshot.stripe_secret_hint}. Laissez vide pour conserver."
            if snapshot.stripe_secret_hint
            else "Clé secrète sk_ ou restricted rk_. Elle ne sera plus affichée ensuite."
        )
        self.fields["stripe_webhook_secret"].help_text = (
            (
                "Valeur enregistrée invalide : ce n’est pas un secret whsec_… "
                "(souvent l’ID d’endpoint we_…). "
                "Dans Stripe → Développeurs → Webhooks → votre endpoint → "
                "« Révéler » le Signing secret, puis collez-le ici."
            )
            if snapshot.stripe_webhook_hint and not snapshot.stripe_webhook_secret_valid
            else (
                f"Enregistré : {snapshot.stripe_webhook_hint}. Laissez vide pour conserver."
                if snapshot.stripe_webhook_hint
                else (
                    "Signing secret whsec_… (pas l’ID we_…). "
                    "Stripe → Développeurs → Webhooks → Révéler le secret."
                )
            )
        )

    def clean(self):
        cleaned = super().clean()
        paypal_id = str(cleaned.get("paypal_client_id") or "").strip()
        paypal_secret = str(cleaned.get("paypal_client_secret") or "").strip()
        if paypal_id and paypal_secret and paypal_id == paypal_secret:
            raise ValidationError(
                {"paypal_client_secret": ("Le Secret PayPal doit être différent du Client ID.")}
            )

        stripe_pk = str(cleaned.get("stripe_publishable_key") or "").strip()
        stripe_sk = str(cleaned.get("stripe_secret_key") or "").strip()
        stored_pk = str(self.snapshot.stripe_publishable_key or "").strip()
        effective_pk = stripe_pk or stored_pk
        errors: dict[str, str] = {}

        if stripe_pk and not stripe_pk.startswith(("pk_test_", "pk_live_")):
            errors["stripe_publishable_key"] = (
                "La clé publiable doit commencer par pk_test_ ou pk_live_."
            )
        if stripe_sk and not stripe_sk.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
            errors["stripe_secret_key"] = (
                "La clé secrète doit commencer par sk_test_/sk_live_ "
                "(ou rk_test_/rk_live_ pour une clé restreinte)."
            )
        stripe_whsec = str(cleaned.get("stripe_webhook_secret") or "").strip()
        if stripe_whsec:
            if stripe_whsec.startswith("we_"):
                errors["stripe_webhook_secret"] = (
                    "Vous avez collé l’ID d’endpoint (we_…), pas le Signing secret. "
                    "Ouvrez le webhook dans Stripe et cliquez « Révéler » sur whsec_…."
                )
            elif not stripe_whsec.startswith("whsec_"):
                errors["stripe_webhook_secret"] = "Le secret webhook doit commencer par whsec_."
        # Détecte l'inversion classique pk_ ↔ sk_ même si un seul champ est resaisi.
        if stripe_sk.startswith(("pk_test_", "pk_live_")) or effective_pk.startswith(
            ("sk_test_", "sk_live_", "rk_test_", "rk_live_")
        ):
            errors["stripe_secret_key"] = (
                "Clés Stripe inversées : la publiable est pk_… et la secrète sk_/rk_…."
            )
            if stripe_pk or effective_pk.startswith(("sk_", "rk_")):
                errors["stripe_publishable_key"] = (
                    "Cette valeur ressemble à une clé secrète. Utilisez la clé pk_…."
                )
        if errors:
            raise ValidationError(errors)
        return cleaned
