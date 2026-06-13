from __future__ import annotations

from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from apps.portal.views_common import access_scope_service


class PortalLoginView(LoginView):
    template_name = "portal/login.html"
    redirect_authenticated_user = True

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
