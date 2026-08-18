from __future__ import annotations

from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views import View

from apps.accounts.forms import AccountClosureForm
from apps.accounts.services.privacy import PrivacyRightsService
from apps.portal.views_common import access_scope_service

privacy_rights_service = PrivacyRightsService()


def _client_ip(request) -> str | None:
    return (request.META.get("REMOTE_ADDR") or "").strip() or None


def _nav_mode(request) -> str:
    requested_space = request.POST.get("space") or request.GET.get("space")
    if requested_space == "staff" and access_scope_service.can_access_staff_portal(request.user):
        return "staff"
    return "client"


def _privacy_context(request, *, form=None, error: str = "") -> dict[str, object]:
    nav_mode = _nav_mode(request)
    context: dict[str, object] = {
        "nav_key": "account-profile",
        "nav_mode": nav_mode,
        "account_section": "privacy",
        "closure_form": form or AccountClosureForm(user=request.user),
        "can_self_close": not (
            request.user.is_staff or request.user.has_perm("accounts.access_staff_portal")
        ),
        "closure_error": error,
    }
    if nav_mode != "client":
        return context
    scope = access_scope_service.get_user_scope(request.user)
    selected_membership = scope.memberships[0] if scope.memberships else None
    customer = None
    if selected_membership is not None:
        customer = (
            access_scope_service.get_customer_queryset(request.user)
            .filter(public_id=selected_membership.customer_public_id)
            .first()
        )
    context.update({"customer": customer, "selected_membership": selected_membership})
    return context


class PortalPrivacyView(LoginRequiredMixin, View):
    template_name = "portal/privacy.html"

    def get(self, request):
        return render(request, self.template_name, _privacy_context(request))


class PortalPrivacyExportView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        payload = privacy_rights_service.export_user_data_json(user=request.user)
        filename = f"prenium-dtf-mes-donnees-{timezone.now().date().isoformat()}.json"
        response = HttpResponse(payload, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Content-Length"] = str(len(payload))
        return response


class PortalPrivacyCloseView(LoginRequiredMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        form = AccountClosureForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(
                request,
                PortalPrivacyView.template_name,
                _privacy_context(request, form=form),
                status=400,
            )
        try:
            privacy_rights_service.close_account(
                user=request.user,
                actor=request.user,
                ip_address=_client_ip(request),
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return render(
                request,
                PortalPrivacyView.template_name,
                _privacy_context(request, form=form, error=message),
                status=400,
            )
        logout(request)
        return HttpResponseRedirect(reverse("portal:account-closed"))


class PortalAccountClosedView(View):
    http_method_names = ["get"]
    template_name = "portal/account_closed.html"

    def get(self, request):
        return render(request, self.template_name)
