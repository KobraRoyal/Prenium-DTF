from django import forms

from apps.branding.models import BrandThemeSettings


class BrandThemeSettingsForm(forms.ModelForm):
    class Meta:
        model = BrandThemeSettings
        fields = ("primary_color", "secondary_color")
        widgets = {
            "primary_color": forms.TextInput(
                attrs={
                    "class": "ui-input brand-color-field__text",
                    "autocomplete": "off",
                    "inputmode": "text",
                    "maxlength": "7",
                    "pattern": "#[0-9A-Fa-f]{6}",
                    "placeholder": "#FF8775",
                    "spellcheck": "false",
                    "x-model": "primary",
                }
            ),
            "secondary_color": forms.TextInput(
                attrs={
                    "class": "ui-input brand-color-field__text",
                    "autocomplete": "off",
                    "inputmode": "text",
                    "maxlength": "7",
                    "pattern": "#[0-9A-Fa-f]{6}",
                    "placeholder": "#A83BC4",
                    "spellcheck": "false",
                    "x-model": "secondary",
                }
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        for field_name in ("primary_color", "secondary_color"):
            value = cleaned_data.get(field_name)
            if value:
                cleaned_data[field_name] = value.strip().upper()
        if cleaned_data.get("primary_color") and cleaned_data.get(
            "primary_color"
        ) == cleaned_data.get("secondary_color"):
            self.add_error(
                "secondary_color",
                "Choisissez une couleur secondaire différente de la couleur primaire.",
            )
        return cleaned_data
