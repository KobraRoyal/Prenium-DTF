import re

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import ProspectProfile


class ProspectStep1Form(forms.Form):
    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Email professionnel")
    phone = forms.CharField(label="Téléphone", max_length=32)
    company = forms.CharField(label="Société", max_length=255)
    country = forms.ChoiceField(
        label="Pays",
        choices=[
            ("FR", "France"),
            ("BE", "Belgique"),
            ("CH", "Suisse"),
            ("DE", "Allemagne"),
            ("ES", "Espagne"),
            ("IT", "Italie"),
            ("NL", "Pays-Bas"),
            ("LU", "Luxembourg"),
            ("AT", "Autriche"),
            ("PT", "Portugal"),
            ("GB", "Royaume-Uni"),
            ("MA", "Maroc"),
            ("TN", "Tunisie"),
            ("CA", "Canada"),
            ("US", "États-Unis"),
            ("ZZ", "Autre pays"),
        ],
    )
    siren = forms.CharField(label="Numéro SIREN", max_length=14, required=False)
    vat_number = forms.CharField(
        label="N° de TVA / identifiant fiscal",
        max_length=40,
        required=False,
    )
    activity_type = forms.ChoiceField(
        label="Type d’activité",
        choices=ProspectProfile.ActivityType.choices,
        widget=forms.RadioSelect,
    )

    def clean_siren(self) -> str:
        return re.sub(r"\D", "", self.cleaned_data.get("siren", ""))

    def clean_vat_number(self) -> str:
        return re.sub(r"[\s.\-]", "", self.cleaned_data.get("vat_number", "")).upper()

    def clean(self):
        data = super().clean()
        country = data.get("country")
        siren = data.get("siren", "")
        vat_number = data.get("vat_number", "")
        if country == "FR" and not re.fullmatch(r"\d{9}", siren):
            self.add_error("siren", "Saisissez les 9 chiffres du numéro SIREN.")
        if country and country != "FR" and not re.fullmatch(r"[A-Z0-9]{4,32}", vat_number):
            self.add_error(
                "vat_number",
                "Saisissez un numéro de TVA ou identifiant fiscal valide.",
            )
        return data


class ProspectStep2Form(forms.Form):
    service_interest = forms.ChoiceField(
        label="Service qui vous intéresse",
        choices=ProspectProfile.ServiceInterest.choices,
        widget=forms.RadioSelect,
    )
    main_goal = forms.CharField(
        label="Objectif principal",
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    project_timing = forms.ChoiceField(
        label="Votre besoin",
        choices=ProspectProfile.ProjectTiming.choices,
        widget=forms.RadioSelect,
    )
    monthly_volume = forms.ChoiceField(
        label="Volume mensuel estimé",
        choices=ProspectProfile.MonthlyVolume.choices,
        widget=forms.RadioSelect,
    )
    order_frequency = forms.ChoiceField(
        label="Fréquence de commande",
        choices=ProspectProfile.OrderFrequency.choices,
        widget=forms.RadioSelect,
    )
    urgency = forms.ChoiceField(
        label="Niveau d’urgence",
        choices=ProspectProfile.Urgency.choices,
        widget=forms.RadioSelect,
    )


class ProspectStep3ReviewForm(forms.Form):
    terms_accepted = forms.BooleanField(
        label=(
            "Je confirme l'exactitude des informations et accepte d'être contacté "
            "dans le cadre de cette demande d'accès."
        )
    )


class ProspectActivationForm(forms.Form):
    password = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_password(self):
        pwd = self.cleaned_data["password"]
        validate_password(pwd)
        return pwd

    def clean(self):
        data = super().clean()
        p1 = data.get("password")
        p2 = data.get("password_confirm")
        if p1 and p2 and p1 != p2:
            raise ValidationError("Les deux mots de passe ne correspondent pas.")
        return data


class ProspectApprovalForm(forms.Form):
    review_note = forms.CharField(
        label="Note interne",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class ProspectRejectionForm(ProspectApprovalForm):
    rejection_reason = forms.CharField(
        label="Motif communiqué au prospect",
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
