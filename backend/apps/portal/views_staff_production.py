from __future__ import annotations

import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.gang_sheets.models import GangSheet
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    access_scope_service,
    badge_tone_for_status,
    meterage_context_for_order,
    production_workflow_service,
    status_label,
)
from apps.portal.views_staff import StaffOrderContextMixin
from apps.production.models import ProductionMachine


def production_panel_context(
    *,
    request,
    order,
    job,
    transition_error: str = "",
    machine_error: str = "",
    print_error: str = "",
):
    from apps.billing.services.production_payment_gate import (
        order_awaits_client_payment,
        production_start_blocked_reason,
    )

    meterage = meterage_context_for_order(request, order, "")
    payment_block = production_start_blocked_reason(order)
    active_machines = ProductionMachine.objects.active().order_by("code", "name")
    return {
        "order": order,
        "job": job,
        "allowed_statuses": production_workflow_service.allowed_target_statuses(
            current_status=job.status,
            order=order,
        ),
        "can_transition": request.user.has_perm("production.transition_productionjob"),
        "can_assign_machine": request.user.has_perm("production.assign_productionmachine"),
        "can_confirm_print": request.user.has_perm("production.confirm_productionprint"),
        "can_confirm_print_now": job.status in {"in_progress", "ready_to_ship"},
        "is_reprint": job.print_records.exists(),
        "print_count": job.print_records.count(),
        "active_machines": active_machines,
        "transition_error": transition_error,
        "machine_error": machine_error,
        "print_error": print_error,
        "print_request_token": uuid.uuid4(),
        "production_payment_blocked": payment_block is not None,
        "production_payment_block_reason": payment_block or "",
        "awaits_client_payment": order_awaits_client_payment(order),
        "meterage_hx_target": "#staff-order-meterage-slot-production",
        "gang_sheets": GangSheet.objects.for_order(order).filter(status=GangSheet.Status.VALIDATED),
        "can_download_gang_sheet_final": request.user.has_perm(
            "gang_sheets.download_final_gangsheet"
        ),
        **meterage,
        "badge_tone_for_status": badge_tone_for_status,
        "status_label": status_label,
    }


class StaffOrderPanelProductionView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/production.html"

    def dispatch(self, request, *args, **kwargs):
        if not access_scope_service.can_access_staff_portal(request.user) or any(
            not request.user.has_perm(permission)
            for permission in ("orders.view_order", "production.view_productionjob")
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _production_panel_context(self, request, job, transition_error: str = ""):
        return production_panel_context(
            request=request,
            order=self.order,
            job=job,
            transition_error=transition_error,
        )

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
