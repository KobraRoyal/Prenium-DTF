from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.views import (
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.urls import reverse_lazy


def _password_reset_email_context() -> dict[str, str]:
    parsed = urlparse(str(getattr(settings, "PUBLIC_BASE_URL", "") or "http://localhost:8080"))
    return {
        "domain": parsed.netloc or "localhost:8080",
        "site_name": str(getattr(settings, "LEGAL_BRAND_NAME", "Prenium DTF")),
        "protocol": parsed.scheme or "https",
    }


class PortalPasswordResetView(PasswordResetView):
    template_name = "portal/password_reset_form.html"
    email_template_name = "portal/emails/password_reset.txt"
    subject_template_name = "portal/emails/password_reset_subject.txt"
    success_url = reverse_lazy("portal:password-reset-done")
    extra_email_context = None

    def form_valid(self, form):
        self.extra_email_context = _password_reset_email_context()
        return super().form_valid(form)


class PortalPasswordResetDoneView(PasswordResetDoneView):
    template_name = "portal/password_reset_done.html"


class PortalPasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "portal/password_reset_confirm.html"
    success_url = reverse_lazy("portal:password-reset-complete")


class PortalPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "portal/password_reset_complete.html"
