from django import forms
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm

from .models import User


class UserCreationForm(DjangoUserCreationForm):
    class Meta(DjangoUserCreationForm.Meta):
        model = User
        fields = ("email", "first_name", "last_name")


class UserChangeForm(DjangoUserChangeForm):
    class Meta(DjangoUserChangeForm.Meta):
        model = User
        fields = "__all__"


class ProfileInformationForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name")


class AccountClosureForm(forms.Form):
    confirmation = forms.CharField(
        label="Confirmez en saisissant votre e-mail de connexion",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )

    def __init__(self, *args, user: User, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_confirmation(self):
        value = str(self.cleaned_data.get("confirmation") or "").strip().lower()
        if value != self.user.email.strip().lower():
            raise forms.ValidationError(
                "Saisissez votre e-mail de connexion pour confirmer la clôture."
            )
        return value
