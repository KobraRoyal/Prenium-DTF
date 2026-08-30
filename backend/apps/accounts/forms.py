from django import forms
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm

from apps.accounts.models import StaffMembership

from .models import User

AUTH_EMAIL_REQUIRED = "Indiquez votre email professionnel."
AUTH_EMAIL_INVALID = "Indiquez un email valide."
AUTH_PASSWORD_REQUIRED = "Indiquez votre mot de passe."
AUTH_PASSWORD_CONFIRM_REQUIRED = "Confirmez votre mot de passe."
AUTH_INVALID_LOGIN = "Email ou mot de passe incorrect. Vérifiez vos informations puis réessayez."


class StaffInvitationForm(forms.Form):
    email = forms.EmailField(label="E-mail professionnel")
    role = forms.ChoiceField(
        label="Rôle",
        choices=(
            (StaffMembership.Role.ADMIN, "Administrateur"),
            (StaffMembership.Role.MEMBER, "Collaborateur"),
            (StaffMembership.Role.READONLY, "Lecture seule"),
        ),
        initial=StaffMembership.Role.MEMBER,
    )


class StaffMemberRoleForm(forms.Form):
    role = forms.ChoiceField(
        label="Rôle",
        choices=(
            (StaffMembership.Role.ADMIN, "Administrateur"),
            (StaffMembership.Role.MEMBER, "Collaborateur"),
            (StaffMembership.Role.READONLY, "Lecture seule"),
        ),
    )


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


class PortalAuthenticationForm(AuthenticationForm):
    error_messages = {
        "invalid_login": AUTH_INVALID_LOGIN,
        "inactive": "Ce compte est inactif. Contactez votre interlocuteur Prenium DTF.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email professionnel"
        self.fields["username"].error_messages.update(
            {
                "required": AUTH_EMAIL_REQUIRED,
                "invalid": AUTH_EMAIL_INVALID,
            }
        )
        self.fields["password"].error_messages["required"] = AUTH_PASSWORD_REQUIRED


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="Email professionnel",
        error_messages={
            "required": AUTH_EMAIL_REQUIRED,
            "invalid": AUTH_EMAIL_INVALID,
        },
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
        self.fields["new_password1"].error_messages["required"] = AUTH_PASSWORD_REQUIRED
        self.fields["new_password2"].error_messages["required"] = AUTH_PASSWORD_CONFIRM_REQUIRED
        for name in ("new_password1", "new_password2"):
            self.fields[name].widget.attrs.update(
                {
                    "class": "ui-input",
                    "autocomplete": "new-password",
                }
            )
