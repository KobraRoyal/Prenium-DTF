from __future__ import annotations

from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.pod.services.qc import PodQcService
from apps.pod.services.ready_inbox import PodReadyInboxService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav

qc_service = PodQcService()
ready_inbox_service = PodReadyInboxService()


class StaffPodQcView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/qc.html"

    def _context(self, request, *, lookup=None, form_error=""):
        return {
            **_nav(),
            "pending_units": qc_service.list_pending(actor=request.user, limit=30),
            "ready_orders": ready_inbox_service.list_recent(actor=request.user, limit=8),
            "lookup": lookup,
            "form_error": form_error,
            "can_manage_qc": request.user.has_perm("pod.operate_pod_production"),
            "pod_ready_context": True,
            "scan_identifier": (
                request.POST.get("scan_identifier") or request.GET.get("scan", "")
            ).strip(),
            "submitted_defect_code": request.POST.get("defect_code", "").strip(),
            "submitted_note": request.POST.get("note", "").strip(),
            "submitted_decision": request.POST.get("decision", ""),
            "outcome": request.GET.get("outcome", ""),
        }

    def _render_error(self, request, exc: ValidationError, *, lookup=None):
        return render(
            request,
            self.template_name,
            self._context(
                request,
                lookup=lookup,
                form_error=validation_message(exc),
            ),
            status=400,
        )

    def get(self, request):
        lookup = None
        scan = request.GET.get("scan", "").strip()
        if scan:
            try:
                lookup = qc_service.lookup(actor=request.user, scan_identifier=scan)
            except ValidationError as exc:
                return self._render_error(request, exc)
        return render(request, self.template_name, self._context(request, lookup=lookup))

    def post(self, request):
        scan = request.POST.get("scan_identifier", "").strip()
        intent = request.POST.get("intent", "lookup")
        lookup = None
        try:
            if intent == "lookup":
                lookup = qc_service.lookup(actor=request.user, scan_identifier=scan)
            elif intent == "decide":
                decision = request.POST.get("decision", "")
                if decision not in {"pass", "fail"}:
                    raise ValidationError("Décision de contrôle qualité inconnue.")
                passed = decision == "pass"
                qc_service.decide(
                    actor=request.user,
                    scan_identifier=scan,
                    passed=passed,
                    defect_code=request.POST.get("defect_code", ""),
                    note=request.POST.get("note", ""),
                    source="staff_pod",
                )
                outcome = "passed" if passed else "failed"
                return self._success_redirect(outcome)
            elif intent == "reopen":
                qc_service.reopen(
                    actor=request.user,
                    scan_identifier=scan,
                    source="staff_pod",
                )
                return self._success_redirect("reopened", scan=scan)
            else:
                raise ValidationError("Action de contrôle qualité inconnue.")
        except PermissionDenied:
            raise
        except ValidationError as exc:
            if intent in {"decide", "reopen"} and scan:
                try:
                    lookup = qc_service.lookup(actor=request.user, scan_identifier=scan)
                except ValidationError:
                    lookup = None
            return self._render_error(request, exc, lookup=lookup)
        return render(request, self.template_name, self._context(request, lookup=lookup))

    @staticmethod
    def _success_redirect(outcome: str, *, scan=""):
        params = {"outcome": outcome}
        if scan:
            params["scan"] = scan.strip().upper()
        return HttpResponseRedirect(f"{reverse('portal:staff-pod-qc')}?{urlencode(params)}")
