from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.accounts.forms import EmailChangeRequestForm
from apps.accounts.services.email_change import EmailChangeService
from apps.portal.views_common import access_scope_service

email_change_service = EmailChangeService()


def _client_ip(request) -> str | None:
    return (request.META.get("REMOTE_ADDR") or "").strip() or None


def _nav_mode(request) -> str:
    requested_space = request.POST.get("space") or request.GET.get("space")
    if requested_space == "staff" and access_scope_service.can_access_staff_portal(request.user):
        return "staff"
    return "client"


def _page_context(request, *, form, error: str = "") -> dict[str, object]:
    nav_mode = _nav_mode(request)
    context: dict[str, object] = {
        "nav_key": "account-profile",
        "nav_mode": nav_mode,
        "account_section": "identity",
        "form": form,
        "error": error,
        "sent": request.GET.get("sent") == "1",
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


class PortalEmailChangeView(LoginRequiredMixin, View):
    template_name = "portal/email_change.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            _page_context(request, form=EmailChangeRequestForm(user=request.user)),
        )

    def post(self, request):
        form = EmailChangeRequestForm(request.POST, user=request.user)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                _page_context(request, form=form),
                status=400,
            )
        try:
            email_change_service.request_change(
                user=request.user,
                new_email=form.cleaned_data["new_email"],
                ip_address=_client_ip(request),
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return render(
                request,
                self.template_name,
                _page_context(request, form=form, error=message),
                status=400,
            )
        space = _nav_mode(request)
        return HttpResponseRedirect(f"{reverse('portal:email-change')}?space={space}&sent=1")


class PortalEmailChangeConfirmView(LoginRequiredMixin, View):
    http_method_names = ["get"]
    template_name = "portal/email_change.html"

    def get(self, request, token: str):
        try:
            email_change_service.confirm_change(
                user=request.user,
                token=token,
                ip_address=_client_ip(request),
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            return render(
                request,
                self.template_name,
                _page_context(
                    request,
                    form=EmailChangeRequestForm(user=request.user),
                    error=message,
                ),
                status=400,
            )
        space = _nav_mode(request)
        return HttpResponseRedirect(f"{reverse('portal:profile')}?space={space}&email_changed=1")
