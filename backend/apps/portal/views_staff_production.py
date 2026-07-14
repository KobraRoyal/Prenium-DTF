from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    badge_tone_for_status,
    meterage_context_for_order,
    production_scan_service,
    production_workflow_service,
    status_label,
)
from apps.portal.views_staff import StaffOrderContextMixin


class StaffOrderPanelProductionView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/production.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("production.view_productionjob"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _production_panel_context(self, request, job, transition_error: str = ""):
        meterage = meterage_context_for_order(request, self.order, "")
        return {
            "order": self.order,
            "job": job,
            "allowed_statuses": production_workflow_service.allowed_target_statuses(
                current_status=job.status
            ),
            "can_transition": request.user.has_perm("production.transition_productionjob"),
            "transition_error": transition_error,
            "meterage_hx_target": "#staff-order-meterage-slot-production",
            **meterage,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        _, job = production_workflow_service.get_staff_job(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        if job is None:
            raise Http404
        self.order.refresh_from_db()
        return render(
            request,
            self.template_name,
            self._production_panel_context(request, job, ""),
        )

    def post(self, request, order_public_id):
        if not request.user.has_perm("production.transition_productionjob"):
            raise PermissionDenied
        transition_error = ""
        try:
            _, job, _transition = production_workflow_service.transition_job(
                order_public_id=self.order.public_id,
                to_status=request.POST.get("to_status", ""),
                actor=request.user,
                reason=request.POST.get("reason", ""),
                source="staff_portal",
            )
        except ValidationError as exc:
            job = production_workflow_service.get_or_create_for_order(order=self.order)
            transition_error = "; ".join(exc.messages)
        self.order.refresh_from_db()
        response = render(
            request,
            self.template_name,
            self._production_panel_context(request, job, transition_error),
        )
        if transition_error:
            return with_toast(response, transition_error, "error")
        return with_toast(response, "Transition enregistree.", "success")


class StaffOrderPanelScanView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/scan.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("production.scan_productionjob"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        job = production_workflow_service.get_or_create_for_order(order=self.order)
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "job": job,
                "scan_result": None,
                "scan_error": "",
                "can_scan_transition": request.user.has_perm(
                    "production.scan_transition_productionjob"
                ),
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )

    def post(self, request, order_public_id):
        scan_error = ""
        scan_result = None
        scan_identifier = request.POST.get("scan_identifier", "")
        to_status = request.POST.get("to_status", "").strip()
        reason = request.POST.get("reason", "")

        try:
            if to_status:
                if not request.user.has_perm("production.scan_transition_productionjob"):
                    raise PermissionDenied
                job, _transition = production_scan_service.transition_by_scan(
                    scan_identifier=scan_identifier,
                    to_status=to_status,
                    actor=request.user,
                    reason=reason,
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
            {
                "order": self.order,
                "job": production_workflow_service.get_or_create_for_order(order=self.order),
                "scan_result": scan_result,
                "scan_error": scan_error,
                "can_scan_transition": request.user.has_perm(
                    "production.scan_transition_productionjob"
                ),
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
        if scan_error:
            return with_toast(response, scan_error, "error")
        return with_toast(response, "Scan enregistre.", "success")
