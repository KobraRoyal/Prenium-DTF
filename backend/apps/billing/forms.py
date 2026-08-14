from __future__ import annotations

from datetime import date, datetime, timedelta

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone


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
