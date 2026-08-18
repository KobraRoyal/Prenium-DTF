from django.urls import path

from .views import (
    AccordSousTraitanceView,
    HealthcheckView,
    MarketingHomeView,
    MarketingServicesView,
    MentionsLegalesView,
    PolitiqueConfidentialiteView,
    PolitiqueCookiesView,
)

urlpatterns = [
    path("", MarketingHomeView.as_view(), name="home"),
    path("services/", MarketingServicesView.as_view(), name="services"),
    path("mentions-legales/", MentionsLegalesView.as_view(), name="mentions-legales"),
    path(
        "politique-de-confidentialite/",
        PolitiqueConfidentialiteView.as_view(),
        name="politique-confidentialite",
    ),
    path("politique-cookies/", PolitiqueCookiesView.as_view(), name="politique-cookies"),
    path(
        "accord-sous-traitance/",
        AccordSousTraitanceView.as_view(),
        name="accord-sous-traitance",
    ),
    path("healthz/", HealthcheckView.as_view(), name="healthcheck"),
]
