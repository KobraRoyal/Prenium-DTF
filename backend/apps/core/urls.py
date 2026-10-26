from django.urls import path

from .services.legal import LEGAL_PAGES
from .views import HealthcheckView, LegalPageView, MarketingHomeView, MarketingServicesView

urlpatterns = [
    path("", MarketingHomeView.as_view(), name="home"),
    path("services/", MarketingServicesView.as_view(), name="services"),
    path("healthz/", HealthcheckView.as_view(), name="healthcheck"),
    *[
        path(page.path, LegalPageView.as_view(page=page), name=page.url_name)
        for page in LEGAL_PAGES
    ],
]
