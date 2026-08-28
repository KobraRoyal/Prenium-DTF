from __future__ import annotations

from django.conf import settings
from django.contrib.auth.views import (
    INTERNAL_RESET_SESSION_TOKEN,
    LoginView,
    LogoutView,
    PasswordResetConfirmView,
)
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from apps.accounts.forms import (
    PasswordResetRequestForm,
    PortalAuthenticationForm,
    PortalSetPasswordForm,
)
from apps.accounts.middleware import _client_ip
from apps.accounts.services.password_reset import password_reset_service
from apps.portal.views_common import access_scope_service


def auth_support_context() -> dict[str, str]:
    return {"support_contact_email": str(getattr(settings, "SUPPORT_CONTACT_EMAIL", "") or "")}


class PortalLoginView(LoginView):
    template_name = "portal/login.html"
    authentication_form = PortalAuthenticationForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(auth_support_context())
        return context

    def get_success_url(self):
        redirect_to = self.get_redirect_url()
        if redirect_to and url_has_allowed_host_and_scheme(
            url=redirect_to,
            allowed_hosts={self.request.get_host()},
            require_https=self.request.is_secure(),
        ):
            return redirect_to
        if access_scope_service.can_access_staff_portal(self.request.user):
            return reverse("portal:staff-dashboard")
        return reverse("portal:client-dashboard")


class PortalLogoutView(LogoutView):
    next_page = "/login/"


class PortalPasswordResetRequestView(View):
    template_name = "portal/password_reset_request.html"
    form_class = PasswordResetRequestForm

    def get(self, request):
        return render(
            request,
            self.template_name,
            {"form": self.form_class(), **auth_support_context()},
        )

    def post(self, request):
        form = self.form_class(request.POST)
        if not form.is_valid():
            return render(
                request,
                self.template_name,
                {"form": form, **auth_support_context()},
            )
        password_reset_service.request_reset(
            email=form.cleaned_data["email"],
            ip_address=_client_ip(request),
        )
        return redirect("portal:password-reset-done")


class PortalPasswordResetDoneView(View):
    template_name = "portal/password_reset_done.html"

    def get(self, request):
        return render(request, self.template_name, auth_support_context())


class PortalPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "portal/password_reset_confirm.html"
    success_url = reverse_lazy("portal:password-reset-complete")
    form_class = PortalSetPasswordForm
    reset_url_token = "nouveau"

    def get_user(self, uidb64):
        return password_reset_service.resolve_user(uidb64)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(auth_support_context())
        return context

    def form_valid(self, form):
        password_reset_service.complete_reset(
            user=self.user,
            password=form.cleaned_data["new_password1"],
            ip_address=_client_ip(self.request),
        )
        del self.request.session[INTERNAL_RESET_SESSION_TOKEN]
        return redirect(self.get_success_url())


class PortalPasswordResetCompleteView(View):
    template_name = "portal/password_reset_complete.html"

    def get(self, request):
        return render(request, self.template_name, auth_support_context())
