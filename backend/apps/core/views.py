import os

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.catalog.services.catalog import CatalogQueryService

from .services.health import HealthcheckService

catalog_query_service = CatalogQueryService()


def marketing_home_redirects_to_login() -> bool:
    """Prod only by default; override via MARKETING_HOME_REDIRECT_TO_LOGIN."""
    explicit = os.environ.get("MARKETING_HOME_REDIRECT_TO_LOGIN", "").strip().lower()
    if explicit in {"1", "true", "yes", "on"}:
        return True
    if explicit in {"0", "false", "no", "off"}:
        return False
    module = (
        getattr(settings, "SETTINGS_MODULE", "")
        or os.environ.get("DJANGO_SETTINGS_MODULE", "")
        or ""
    )
    return module.endswith(".prod")


class HealthcheckView(View):
    http_method_names = ["get"]

    def get(self, request, *args, **kwargs):
        service = HealthcheckService()
        payload = service.get_payload()
        status_code = 200 if payload["status"] == "ok" else 503
        return JsonResponse(payload, status=status_code)


class MarketingHomeView(View):
    http_method_names = ["get"]
    template_name = "shop/home.html"

    def get(self, request, *args, **kwargs):
        if marketing_home_redirects_to_login():
            return redirect("portal:login")
        services = list(catalog_query_service.list_active_services()[:2])
        return render(
            request,
            self.template_name,
            {
                "services": services,
            },
        )


class MarketingServicesView(View):
    http_method_names = ["get"]
    template_name = "shop/services.html"

    def get(self, request, *args, **kwargs):
        services = list(catalog_query_service.list_active_services())
        return render(
            request,
            self.template_name,
            {
                "services": services,
            },
        )


class LegalPageView(View):
    """Pages publiques d'information (accessibles même si l'accueil redirige vers le login)."""

    http_method_names = ["get"]
    template_name = ""

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name)


class MentionsLegalesView(LegalPageView):
    template_name = "shop/legal/mentions.html"


class PolitiqueConfidentialiteView(LegalPageView):
    template_name = "shop/legal/privacy.html"


class PolitiqueCookiesView(LegalPageView):
    template_name = "shop/legal/cookies.html"


class AccordSousTraitanceView(LegalPageView):
    template_name = "shop/legal/dpa.html"
