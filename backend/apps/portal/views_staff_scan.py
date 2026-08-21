from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    badge_tone_for_status,
    production_scan_service,
    production_workflow_service,
    status_label,
)
from apps.portal.views_staff import StaffOrderContextMixin


class StaffOrderPanelScanView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/scan.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("production.scan_productionjob"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _context(self, request, *, scan_result=None, scan_error=""):
        return {
            "order": self.order,
            "job": production_workflow_service.get_or_create_for_order(order=self.order),
            "scan_result": scan_result,
            "scan_error": scan_error,
            "can_scan_transition": request.user.has_perm(
                "production.scan_transition_productionjob"
            ),
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        return render(request, self.template_name, self._context(request))

    def post(self, request, order_public_id):
        scan_error = ""
        scan_result = None
        scan_identifier = request.POST.get("scan_identifier", "")
        to_status = request.POST.get("to_status", "").strip()
        try:
            if to_status:
                if not request.user.has_perm("production.scan_transition_productionjob"):
                    raise PermissionDenied
                job, _transition = production_scan_service.transition_by_scan(
                    scan_identifier=scan_identifier,
                    to_status=to_status,
                    actor=request.user,
                    reason=request.POST.get("reason", ""),
                    source="staff_portal",
                )
                scan_result = {"job": job, "mode": "transition"}
            else:
                job = production_scan_service.resolve_scan(
                    scan_identifier=scan_identifier,
                    actor=request.user,
                    source="staff_portal",
                )
                scan_result = {"job": job, "mode": "resolve"}
        except ValidationError as exc:
            scan_error = "; ".join(exc.messages)
        response = render(
            request,
            self.template_name,
            self._context(request, scan_result=scan_result, scan_error=scan_error),
        )
        if scan_error:
            return with_toast(response, scan_error, "error")
        return with_toast(response, "Scan enregistre.", "success")
