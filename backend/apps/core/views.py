from django.http import JsonResponse
from django.shortcuts import render
from django.views import View

from apps.catalog.services.catalog import CatalogQueryService

from .services.health import HealthcheckService

catalog_query_service = CatalogQueryService()


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
