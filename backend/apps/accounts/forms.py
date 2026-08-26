from django import forms
from django.contrib.auth.forms import SetPasswordForm
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


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="Email professionnel",
        widget=forms.EmailInput(
            attrs={
                "class": "ui-input",
                "autocomplete": "email",
                "placeholder": "vous@entreprise.fr",
                "autofocus": True,
            }
        ),
    )


class PortalSetPasswordForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password2"].label = "Confirmation"
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.update(
                {
                    "class": "ui-input",
                    "autocomplete": "new-password",
                }
            )
