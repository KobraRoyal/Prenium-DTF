from __future__ import annotations

import hashlib

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from .forms import ProspectStep1Form, ProspectStep2Form, ProspectStep3ReviewForm
from .models import ProspectProfile
from .services.onboarding import ProspectDraft, ProspectOnboardingError, ProspectOnboardingService
from .session import clear_draft, get_draft, has_steps, update_draft
from .stepper import stepper_items_for_step

TOTAL_STEPS = 3


def _client_ip(request: HttpRequest) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if getattr(settings, "PROSPECT_RATE_LIMIT_TRUST_X_FORWARDED_FOR", False) and forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _draft_to_dataclass(request: HttpRequest) -> ProspectDraft | None:
    draft = get_draft(request)
    step1, step2 = draft.get("step1"), draft.get("step2")
    if not all(isinstance(step, dict) and step for step in (step1, step2)):
        return None
    return ProspectDraft(step1=step1, step2=step2)


def _submission_rate_limited(request: HttpRequest, email: str) -> bool:
    identity = f"{_client_ip(request) or 'unknown'}:{email.strip().lower()}"
    digest = hashlib.sha256(identity.encode()).hexdigest()
    key = f"prospect-submit:{digest}"
    window = int(getattr(settings, "PROSPECT_RATE_LIMIT_WINDOW_SECONDS", 3600))
    maximum = int(getattr(settings, "PROSPECT_RATE_LIMIT_MAX_ATTEMPTS", 5))
    if cache.add(key, 1, timeout=window):
        return False
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        return False
    return attempts > maximum


def _context(step: int, **extra) -> dict:
    return {
        "step": step,
        "total_steps": TOTAL_STEPS,
        "steps": stepper_items_for_step(step, TOTAL_STEPS),
        **extra,
    }


def _choice_label(form_class, field_name: str, value: str) -> str:
    return dict(form_class.base_fields[field_name].choices).get(value, value)


def _summary_for_draft(draft: dict) -> dict[str, str]:
    step1 = draft.get("step1") or {}
    step2 = draft.get("step2") or {}
    return {
        "company": str(step1.get("company") or ""),
        "contact": f"{step1.get('first_name', '')} {step1.get('last_name', '')}".strip(),
        "email": str(step1.get("email") or ""),
        "country": _choice_label(ProspectStep1Form, "country", step1.get("country", "")),
        "legal_id": (
            f"SIREN {step1.get('siren', '')}"
            if step1.get("country") == "FR"
            else str(step1.get("vat_number") or "")
        ),
        "service": _choice_label(
            ProspectStep2Form,
            "service_interest",
            step2.get("service_interest", ""),
        ),
        "volume": _choice_label(
            ProspectStep2Form,
            "monthly_volume",
            step2.get("monthly_volume", ""),
        ),
        "timing": _choice_label(
            ProspectStep2Form,
            "project_timing",
            step2.get("project_timing", ""),
        ),
    }


class ProspectStep1View(View):
    template_name = "prospects/step1.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        form = ProspectStep1Form(initial=get_draft(request).get("step1") or {})
        return render(request, self.template_name, _context(1, form=form))

    def post(self, request: HttpRequest) -> HttpResponse:
        form = ProspectStep1Form(request.POST)
        if form.is_valid():
            update_draft(request, "step1", form.cleaned_data)
            return redirect("prospects:step2")
        return render(request, self.template_name, _context(1, form=form))


class ProspectStep2View(View):
    template_name = "prospects/step2.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1"):
            return redirect("prospects:step1")
        form = ProspectStep2Form(initial=get_draft(request).get("step2") or {})
        return render(request, self.template_name, _context(2, form=form))

    def post(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1"):
            return redirect("prospects:step1")
        form = ProspectStep2Form(request.POST)
        if form.is_valid():
            update_draft(request, "step2", form.cleaned_data)
            return redirect("prospects:step3")
        return render(request, self.template_name, _context(2, form=form))


class ProspectStep3View(View):
    template_name = "prospects/step3.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1", "step2"):
            return redirect("prospects:step1")
        draft = get_draft(request)
        return render(
            request,
            self.template_name,
            _context(
                3,
                form=ProspectStep3ReviewForm(),
                draft=draft,
                summary=_summary_for_draft(draft),
            ),
        )

    def post(self, request: HttpRequest) -> HttpResponse:
        if not has_steps(request, "step1", "step2"):
            return redirect("prospects:step1")
        form = ProspectStep3ReviewForm(request.POST)
        draft = _draft_to_dataclass(request)
        if draft is None:
            messages.error(request, "Session expirée. Recommencez votre demande.")
            return redirect("prospects:step1")
        if not form.is_valid():
            draft_data = get_draft(request)
            return render(
                request,
                self.template_name,
                _context(
                    3,
                    form=form,
                    draft=draft_data,
                    summary=_summary_for_draft(draft_data),
                ),
            )
        if _submission_rate_limited(request, str(draft.step1.get("email", ""))):
            messages.error(
                request,
                "Trop de tentatives ont été détectées. Réessayez dans une heure.",
            )
            draft_data = get_draft(request)
            return render(
                request,
                self.template_name,
                _context(
                    3,
                    form=form,
                    draft=draft_data,
                    summary=_summary_for_draft(draft_data),
                ),
                status=429,
            )
        try:
            profile = ProspectOnboardingService().submit_from_draft(
                draft=draft,
                ip_address=_client_ip(request),
            )
        except ProspectOnboardingError:
            messages.error(
                request,
                "Nous ne pouvons pas enregistrer la demande pour le moment. Réessayez plus tard.",
            )
            draft_data = get_draft(request)
            return render(
                request,
                self.template_name,
                _context(
                    3,
                    form=form,
                    draft=draft_data,
                    summary=_summary_for_draft(draft_data),
                ),
            )
        clear_draft(request)
        request.session["prospect_confirmation_public_id"] = str(profile.public_id)
        return redirect("prospects:confirmation")


class ProspectConfirmationView(View):
    def get(self, request: HttpRequest) -> HttpResponse:
        public_id = request.session.get("prospect_confirmation_public_id")
        profile = ProspectProfile.objects.filter(public_id=public_id).first() if public_id else None
        return render(request, "prospects/confirmation.html", {"profile": profile})


class ProspectEmailVerificationView(View):
    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        try:
            profile = ProspectOnboardingService().verify_email(
                token=token,
                ip_address=_client_ip(request),
            )
        except ProspectOnboardingError as exc:
            return render(
                request,
                "prospects/verification_result.html",
                {"verified": False, "message": str(exc)},
                status=400,
            )
        return render(
            request,
            "prospects/verification_result.html",
            {"verified": True, "profile": profile},
        )
