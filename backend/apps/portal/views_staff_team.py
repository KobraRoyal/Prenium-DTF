from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views import View

from apps.accounts.forms import StaffInvitationForm, StaffMemberRoleForm
from apps.accounts.models import StaffInvitation, StaffMembership
from apps.accounts.services.staff_invitations import StaffInvitationError, StaffInvitationService
from apps.portal.htmx import with_toast
from apps.portal.views_access_management import _client_ip
from apps.portal.views_common import StaffTeamManagerRequiredMixin

staff_invitation_service = StaffInvitationService()


def _pending_staff_invitations():
    return StaffInvitation.objects.filter(
        status=StaffInvitation.Status.PENDING,
    ).select_related("invited_by")


def _staff_team_invite_panel_context(*, form=None, invited_email: str = "") -> dict:
    return {
        "invitation_form": form or StaffInvitationForm(),
        "invitations": _pending_staff_invitations(),
        "invited_email": invited_email,
    }


class StaffTeamView(StaffTeamManagerRequiredMixin, View):
    template_name = "portal/staff/team.html"

    def get(self, request):
        memberships = (
            StaffMembership.objects.select_related("user")
            .order_by("-is_active", "role", "user__email")
        )
        return render(
            request,
            self.template_name,
            {
                "staff_membership": self.staff_membership,
                "memberships": memberships,
                **_staff_team_invite_panel_context(),
                "role_choices": StaffMemberRoleForm.base_fields["role"].choices,
                "nav_mode": "staff",
                "nav_key": "staff-team",
                "account_section": "team",
            },
        )


class StaffTeamInviteView(StaffTeamManagerRequiredMixin, View):
    template_name = "portal/staff/partials/team_invite_panel.html"

    def post(self, request):
        form = StaffInvitationForm(request.POST)
        invited_email = ""
        message = "Vérifiez l’adresse e-mail et le rôle sélectionné."
        variant = "error"
        if form.is_valid():
            try:
                invitation = staff_invitation_service.invite_collaborator(
                    actor=request.user,
                    email=form.cleaned_data["email"],
                    role=form.cleaned_data["role"],
                    ip_address=_client_ip(request),
                )
                invited_email = invitation.email
                message = (
                    f"Invitation créée pour {invitation.email}. "
                    "L’e-mail sécurisé est en cours d’envoi."
                )
                variant = "success"
            except (StaffInvitationError, PermissionDenied) as exc:
                message = str(exc) or "Action non autorisée."

        if request.headers.get("HX-Request"):
            response = render(
                request,
                self.template_name,
                _staff_team_invite_panel_context(
                    form=StaffInvitationForm() if invited_email else form,
                    invited_email=invited_email,
                ),
            )
            return with_toast(response, message, variant)

        if variant == "success":
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect("portal:staff-team")


class StaffTeamInvitationRevokeView(StaffTeamManagerRequiredMixin, View):
    def post(self, request, invitation_public_id):
        try:
            staff_invitation_service.revoke(
                invitation_public_id=invitation_public_id,
                actor=request.user,
                ip_address=_client_ip(request),
            )
            messages.success(request, "Invitation révoquée.")
        except (StaffInvitationError, PermissionDenied):
            messages.error(request, "Cette invitation ne peut pas être révoquée.")
        return redirect("portal:staff-team")


class StaffTeamMemberRoleView(StaffTeamManagerRequiredMixin, View):
    def post(self, request, membership_public_id):
        form = StaffMemberRoleForm(request.POST)
        if form.is_valid():
            try:
                staff_invitation_service.change_member_role(
                    membership_public_id=membership_public_id,
                    actor=request.user,
                    role=form.cleaned_data["role"],
                    ip_address=_client_ip(request),
                )
                messages.success(request, "Rôle mis à jour.")
            except (StaffInvitationError, PermissionDenied):
                messages.error(request, "Ce rôle ne peut pas être modifié.")
        return redirect("portal:staff-team")


class StaffTeamMemberDeactivateView(StaffTeamManagerRequiredMixin, View):
    def post(self, request, membership_public_id):
        try:
            staff_invitation_service.deactivate_member(
                membership_public_id=membership_public_id,
                actor=request.user,
                ip_address=_client_ip(request),
            )
            messages.success(request, "Accès du collaborateur désactivé.")
        except (StaffInvitationError, PermissionDenied):
            messages.error(request, "Cet accès ne peut pas être désactivé.")
        return redirect("portal:staff-team")
