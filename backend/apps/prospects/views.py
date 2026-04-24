from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.debug import sensitive_post_parameters

from .forms import (
    ProspectStep1Form,
    ProspectStep2Form,
    ProspectStep3Form,
    ProspectStep4AccountForm,
)
from .services.onboarding import ProspectDraft, ProspectOnboardingError, ProspectOnboardingService
from .session import clear_draft, get_draft, has_steps, update_draft
from .stepper import stepper_items_for_step

PROSPECT_STEPS = ("step1", "step2", "step3")


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _draft_to_dataclass(request) -> ProspectDraft | None:
    d = get_draft(request)
    s1, s2, s3 = d.get("step1"), d.get("step2"), d.get("step3")
    if not all(isinstance(x, dict) and x for x in (s1, s2, s3)):
        return None
    return ProspectDraft(step1=s1, step2=s2, step3=s3)


class ProspectStep1View(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        initial = get_draft(request).get("step1") or {}
        form = ProspectStep1Form(initial=initial)
        return render(
            request,
            "prospects/step1.html",
            {
                "form": form,
                "step": 1,
                "total_steps": 4,
                "steps": stepper_items_for_step(1, 4),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        form = ProspectStep1Form(request.POST)
        if form.is_valid():
            update_draft(request, "step1", form.cleaned_data)
            return redirect("prospects:step2")
        return render(
            request,
            "prospects/step1.html",
            {
                "form": form,
                "step": 1,
                "total_steps": 4,
                "steps": stepper_items_for_step(1, 4),
            },
        )


class ProspectStep2View(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1"):
            return redirect("prospects:step1")
        initial = get_draft(request).get("step2") or {}
        form = ProspectStep2Form(initial=initial)
        return render(
            request,
            "prospects/step2.html",
            {
                "form": form,
                "step": 2,
                "total_steps": 4,
                "steps": stepper_items_for_step(2, 4),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1"):
            return redirect("prospects:step1")
        form = ProspectStep2Form(request.POST)
        if form.is_valid():
            update_draft(request, "step2", form.cleaned_data)
            return redirect("prospects:step3")
        return render(
            request,
            "prospects/step2.html",
            {
                "form": form,
                "step": 2,
                "total_steps": 4,
                "steps": stepper_items_for_step(2, 4),
            },
        )


class ProspectStep3View(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1", "step2"):
            return redirect("prospects:step1")
        initial = get_draft(request).get("step3") or {}
        form = ProspectStep3Form(initial=initial)
        return render(
            request,
            "prospects/step3.html",
            {
                "form": form,
                "step": 3,
                "total_steps": 4,
                "steps": stepper_items_for_step(3, 4),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1", "step2"):
            return redirect("prospects:step1")
        form = ProspectStep3Form(request.POST)
        if form.is_valid():
            update_draft(request, "step3", form.cleaned_data)
            return redirect("prospects:step4")
        return render(
            request,
            "prospects/step3.html",
            {
                "form": form,
                "step": 3,
                "total_steps": 4,
                "steps": stepper_items_for_step(3, 4),
            },
        )


@method_decorator(sensitive_post_parameters("password", "password_confirm"), name="dispatch")
class ProspectStep4View(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1", "step2", "step3"):
            return redirect("prospects:step1")
        form = ProspectStep4AccountForm()
        return render(
            request,
            "prospects/step4.html",
            {
                "form": form,
                "step": 4,
                "total_steps": 4,
                "draft": get_draft(request),
                "steps": stepper_items_for_step(4, 4),
            },
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1", "step2", "step3"):
            return redirect("prospects:step1")
        form = ProspectStep4AccountForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "prospects/step4.html",
                {
                    "form": form,
                    "step": 4,
                    "total_steps": 4,
                    "draft": get_draft(request),
                    "steps": stepper_items_for_step(4, 4),
                },
            )

        draft = _draft_to_dataclass(request)
        if draft is None:
            messages.error(request, "Session expirée ou incomplète. Recommencez depuis l’étape 1.")
            return redirect("prospects:step1")

        service = ProspectOnboardingService()
        try:
            profile = service.complete_from_draft(
                draft=draft,
                password=form.cleaned_data["password"],
                ip_address=_client_ip(request),
            )
        except ProspectOnboardingError as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "prospects/step4.html",
                {
                    "form": form,
                    "step": 4,
                    "total_steps": 4,
                    "draft": get_draft(request),
                    "steps": stepper_items_for_step(4, 4),
                },
            )

        clear_draft(request)
        login(request, profile.user, backend="django.contrib.auth.backends.ModelBackend")
        request.session["prospect_confirmation_public_id"] = str(profile.public_id)
        return redirect("prospects:confirmation")


class ProspectConfirmationView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        if not request.user.is_authenticated:
            return redirect_to_login(next=reverse("prospects:confirmation"))

        from .models import ProspectProfile

        pid = request.session.pop("prospect_confirmation_public_id", None)
        profile = None
        if pid:
            profile = ProspectProfile.objects.select_related("customer").filter(
                public_id=pid,
                user=request.user,
            ).first()
        if profile is None:
            profile = (
                ProspectProfile.objects.select_related("customer")
                .filter(user=request.user)
                .first()
            )
        if profile is None:
            return redirect("portal:client-dashboard")

        customer = profile.customer
        customer_pid = customer.public_id if customer else None
        return render(
            request,
            "prospects/confirmation.html",
            {
                "profile": profile,
                "customer_public_id": customer_pid,
                "customer": customer,
                "nav_mode": "client",
                "nav_key": "client-dashboard",
            },
        )
