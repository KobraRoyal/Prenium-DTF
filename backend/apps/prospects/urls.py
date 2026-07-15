from django.urls import path
from django.views.generic import RedirectView

from .views import (
    ProspectConfirmationView,
    ProspectEmailVerificationView,
    ProspectStep1View,
    ProspectStep2View,
    ProspectStep3View,
)

app_name = "prospects"

urlpatterns = [
    path(
        "demande-acces/",
        RedirectView.as_view(pattern_name="prospects:step1", permanent=False),
        name="demande_acces",
    ),
    path("demande-acces/etape-1/", ProspectStep1View.as_view(), name="step1"),
    path("demande-acces/etape-2/", ProspectStep2View.as_view(), name="step2"),
    path("demande-acces/etape-3/", ProspectStep3View.as_view(), name="step3"),
    path(
        "demande-acces/etape-4/",
        RedirectView.as_view(pattern_name="prospects:step3", permanent=False),
        name="step4",
    ),
    path("demande-acces/confirmation/", ProspectConfirmationView.as_view(), name="confirmation"),
    path(
        "demande-acces/verifier/<str:token>/",
        ProspectEmailVerificationView.as_view(),
        name="verify-email",
    ),
]

# Anciens chemins /compte-pro/ (barre d’adresse) → 301 vers /demande-acces/
urlpatterns += [
    path(
        "compte-pro/etape-1/",
        RedirectView.as_view(pattern_name="prospects:step1", permanent=True),
    ),
    path(
        "compte-pro/etape-2/",
        RedirectView.as_view(pattern_name="prospects:step2", permanent=True),
    ),
    path(
        "compte-pro/etape-3/",
        RedirectView.as_view(pattern_name="prospects:step3", permanent=True),
    ),
    path(
        "compte-pro/etape-4/",
        RedirectView.as_view(pattern_name="prospects:step4", permanent=True),
    ),
    path(
        "compte-pro/confirmation/",
        RedirectView.as_view(pattern_name="prospects:confirmation", permanent=True),
    ),
]
