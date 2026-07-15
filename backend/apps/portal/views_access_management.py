from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.customers.forms import CustomerInvitationForm, CustomerMemberRoleForm
from apps.customers.models import CustomerInvitation, CustomerMembership
from apps.customers.services.invitations import (
    CustomerInvitationError,
    CustomerInvitationService,
    ExistingAccountLoginRequired,
)
from apps.portal.htmx import with_toast
from apps.portal.views_common import ClientTeamManagerRequiredMixin, StaffDomainPermissionMixin
from apps.prospects.forms import (
    ProspectActivationForm,
    ProspectApprovalForm,
    ProspectRejectionForm,
)
from apps.prospects.models import ProspectProfile
from apps.prospects.services.onboarding import ProspectOnboardingError, ProspectReviewService

User = get_user_model()
invitation_service = CustomerInvitationService()
review_service = ProspectReviewService()


def _pending_team_invitations(customer):
    return customer.invitations.filter(
        kind=CustomerInvitation.Kind.COLLABORATOR,
        status=CustomerInvitation.Status.PENDING,
    ).select_related("invited_by")


def _team_invite_panel_context(*, customer, form=None, invited_email: str = "") -> dict:
    return {
        "customer": customer,
        "invitation_form": form or CustomerInvitationForm(),
        "invitations": _pending_team_invitations(customer),
        "invited_email": invited_email,
    }


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class StaffAccessRequestListView(StaffDomainPermissionMixin, View):
    required_permission = "prospects.view_prospectprofile"
    template_name = "portal/staff/access_requests/list.html"

    def get(self, request):
        status = request.GET.get("status", ProspectProfile.Status.PENDING_REVIEW)
        allowed_statuses = set(ProspectProfile.Status.values)
        queryset = ProspectProfile.objects.select_related("reviewed_by", "customer")
        if status in allowed_statuses:
            queryset = queryset.filter(status=status)
        page_obj = Paginator(queryset, 25).get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "page_obj": page_obj,
                "active_status": status,
                "status_choices": ProspectProfile.Status.choices,
                "nav_mode": "staff",
                "nav_key": "staff-access-requests",
            },
        )


class StaffAccessRequestDetailView(StaffDomainPermissionMixin, View):
    required_permission = "prospects.view_prospectprofile"
    template_name = "portal/staff/access_requests/detail.html"

    def get(self, request, profile_public_id):
        profile = get_object_or_404(
            ProspectProfile.objects.select_related("reviewed_by", "customer"),
            public_id=profile_public_id,
        )
        return render(
            request,
            self.template_name,
            {
                "profile": profile,
                "approval_form": ProspectApprovalForm(),
                "rejection_form": ProspectRejectionForm(),
                "can_review": request.user.has_perm("prospects.review_prospectprofile"),
                "nav_mode": "staff",
                "nav_key": "staff-access-requests",
            },
        )


class StaffAccessRequestApproveView(StaffDomainPermissionMixin, View):
    required_permission = "prospects.review_prospectprofile"

    def post(self, request, profile_public_id):
        form = ProspectApprovalForm(request.POST)
        if form.is_valid():
            try:
                review_service.approve(
                    profile_public_id=profile_public_id,
                    actor=request.user,
                    review_note=form.cleaned_data["review_note"],
                    ip_address=_client_ip(request),
                )
                messages.success(request, "La demande est validée. L'invitation a été envoyée.")
            except ProspectOnboardingError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "La note interne est trop longue.")
        return redirect(
            "portal:staff-access-request-detail",
            profile_public_id=profile_public_id,
        )


class StaffAccessRequestRejectView(StaffDomainPermissionMixin, View):
    required_permission = "prospects.review_prospectprofile"

    def post(self, request, profile_public_id):
        form = ProspectRejectionForm(request.POST)
        if form.is_valid():
            try:
                review_service.reject(
                    profile_public_id=profile_public_id,
                    actor=request.user,
                    rejection_reason=form.cleaned_data["rejection_reason"],
                    review_note=form.cleaned_data["review_note"],
                    ip_address=_client_ip(request),
                )
                messages.success(request, "La demande a été refusée et le prospect informé.")
            except ProspectOnboardingError as exc:
                messages.error(request, str(exc))
        else:
            messages.error(request, "Le motif communiqué au prospect est obligatoire.")
        return redirect(
            "portal:staff-access-request-detail",
            profile_public_id=profile_public_id,
        )


class CustomerInvitationAcceptView(View):
    template_name = "portal/access/invitation_accept.html"

    def get(self, request, token):
        try:
            invitation = invitation_service.resolve_token(token)
        except CustomerInvitationError as exc:
            return render(
                request,
                self.template_name,
                {"error": str(exc)},
                status=400,
            )
        existing_user = User.objects.filter(email__iexact=invitation.email).first()
        return render(
            request,
            self.template_name,
            {
                "invitation": invitation,
                "token": token,
                "existing_account": existing_user is not None,
                "email_matches": bool(
                    existing_user is not None
                    and request.user.is_authenticated
                    and request.user.pk == existing_user.pk
                ),
                "form": ProspectActivationForm() if existing_user is None else None,
            },
        )

    def post(self, request, token):
        try:
            invitation = invitation_service.resolve_token(token)
        except CustomerInvitationError as exc:
            return render(request, self.template_name, {"error": str(exc)}, status=400)
        existing_user = User.objects.filter(email__iexact=invitation.email).first()
        form = ProspectActivationForm(request.POST) if existing_user is None else None
        if form is not None and not form.is_valid():
            return render(
                request,
                self.template_name,
                {"invitation": invitation, "token": token, "form": form},
            )
        try:
            invitation_service.accept(
                token=token,
                authenticated_user=request.user,
                password=form.cleaned_data["password"] if form is not None else None,
                ip_address=_client_ip(request),
            )
        except ExistingAccountLoginRequired:
            login_url = reverse("portal:login")
            return redirect(f"{login_url}?next={request.path}")
        except CustomerInvitationError as exc:
            return render(request, self.template_name, {"error": str(exc)}, status=400)
        return redirect("portal:customer-invitation-complete")


class CustomerInvitationCompleteView(View):
    def get(self, request):
        return render(request, "portal/access/invitation_complete.html")


class ClientTeamView(ClientTeamManagerRequiredMixin, View):
    template_name = "portal/client/team.html"

    def get(self, request, customer_public_id):
        memberships = (
            CustomerMembership.objects.for_customer(self.customer)
            .select_related("user")
            .order_by("-is_active", "role", "user__email")
        )
        invite_panel_context = _team_invite_panel_context(customer=self.customer)
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "customer_membership": self.customer_membership,
                "memberships": memberships,
                **invite_panel_context,
                "role_choices": CustomerMemberRoleForm.base_fields["role"].choices,
                "nav_mode": "client",
                "nav_key": "client-team",
            },
        )


class ClientTeamInviteView(ClientTeamManagerRequiredMixin, View):
    template_name = "portal/client/partials/team_invite_panel.html"

    def post(self, request, customer_public_id):
        form = CustomerInvitationForm(request.POST)
        invited_email = ""
        message = "Vérifiez l’adresse e-mail et le rôle sélectionné."
        variant = "error"
        if form.is_valid():
            try:
                invitation = invitation_service.invite_collaborator(
                    customer=self.customer,
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
            except (CustomerInvitationError, PermissionDenied) as exc:
                message = str(exc) or "Action non autorisée."

        if request.headers.get("HX-Request"):
            response = render(
                request,
                self.template_name,
                _team_invite_panel_context(
                    customer=self.customer,
                    form=CustomerInvitationForm() if invited_email else form,
                    invited_email=invited_email,
                ),
            )
            return with_toast(response, message, variant)

        if variant == "success":
            messages.success(request, message)
        else:
            messages.error(request, message)
        return redirect("portal:client-team", customer_public_id=self.customer.public_id)


class ClientTeamInvitationRevokeView(ClientTeamManagerRequiredMixin, View):
    def post(self, request, customer_public_id, invitation_public_id):
        try:
            invitation_service.revoke(
                invitation_public_id=invitation_public_id,
                customer=self.customer,
                actor=request.user,
                ip_address=_client_ip(request),
            )
            messages.success(request, "Invitation révoquée.")
        except (CustomerInvitationError, PermissionDenied):
            messages.error(request, "Cette invitation ne peut pas être révoquée.")
        return redirect("portal:client-team", customer_public_id=self.customer.public_id)


class ClientTeamMemberRoleView(ClientTeamManagerRequiredMixin, View):
    def post(self, request, customer_public_id, membership_public_id):
        form = CustomerMemberRoleForm(request.POST)
        if form.is_valid():
            try:
                invitation_service.change_member_role(
                    membership_public_id=membership_public_id,
                    customer=self.customer,
                    actor=request.user,
                    role=form.cleaned_data["role"],
                    ip_address=_client_ip(request),
                )
                messages.success(request, "Rôle mis à jour.")
            except (CustomerInvitationError, PermissionDenied):
                messages.error(request, "Ce rôle ne peut pas être modifié.")
        return redirect("portal:client-team", customer_public_id=self.customer.public_id)


class ClientTeamMemberDeactivateView(ClientTeamManagerRequiredMixin, View):
    def post(self, request, customer_public_id, membership_public_id):
        try:
            invitation_service.deactivate_member(
                membership_public_id=membership_public_id,
                customer=self.customer,
                actor=request.user,
                ip_address=_client_ip(request),
            )
            messages.success(request, "Accès du collaborateur désactivé.")
        except (CustomerInvitationError, PermissionDenied):
            messages.error(request, "Cet accès ne peut pas être désactivé.")
        return redirect("portal:client-team", customer_public_id=self.customer.public_id)
