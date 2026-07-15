from django import forms

from apps.customers.models import CustomerMembership


class CustomerInvitationForm(forms.Form):
    email = forms.EmailField(label="E-mail professionnel")
    role = forms.ChoiceField(
        label="Rôle",
        choices=(
            (CustomerMembership.Role.ADMIN, "Administrateur"),
            (CustomerMembership.Role.MEMBER, "Collaborateur"),
            (CustomerMembership.Role.READONLY, "Lecture seule"),
        ),
        initial=CustomerMembership.Role.MEMBER,
    )


class CustomerMemberRoleForm(forms.Form):
    role = forms.ChoiceField(
        label="Rôle",
        choices=(
            (CustomerMembership.Role.ADMIN, "Administrateur"),
            (CustomerMembership.Role.MEMBER, "Collaborateur"),
            (CustomerMembership.Role.READONLY, "Lecture seule"),
        ),
    )
