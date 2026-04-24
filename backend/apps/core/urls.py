from django.urls import path

from .views import HealthcheckView, MarketingHomeView, MarketingServicesView

urlpatterns = [
    path("", MarketingHomeView.as_view(), name="home"),
    path("services/", MarketingServicesView.as_view(), name="services"),
    path("healthz/", HealthcheckView.as_view(), name="healthcheck"),
]
