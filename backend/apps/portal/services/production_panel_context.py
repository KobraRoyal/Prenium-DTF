from __future__ import annotations

import uuid

from apps.gang_sheets.models import GangSheet
from apps.portal.order_status_presentation import handover_date_label
from apps.portal.views_common import (
    badge_tone_for_status,
    meterage_context_for_order,
    production_workflow_service,
    status_label,
)
from apps.production.models import ProductionJob, ProductionMachine


def build_production_panel_context(
    *,
    request,
    order,
    job,
    transition_error: str = "",
    machine_error: str = "",
    print_error: str = "",
    handover_date_error: str = "",
):
    from apps.billing.services.production_payment_gate import (
        order_awaits_client_payment,
        production_start_blocked_reason,
    )

    meterage = meterage_context_for_order(request, order, "")
    payment_block = production_start_blocked_reason(order)
    active_machines = list(ProductionMachine.objects.active().order_by("code", "name"))
    assignment_count = job.machine_assignments.count()
    print_count = job.print_records.count()
    can_assign_machine_now = job.status in {
        ProductionJob.Status.QUEUED,
        ProductionJob.Status.IN_PROGRESS,
        ProductionJob.Status.BLOCKED,
    }
    require_machine_selection = len(active_machines) > 1
    return {
        "order": order,
        "job": job,
        "allowed_statuses": production_workflow_service.allowed_target_statuses(
            current_status=job.status,
            order=order,
        ),
        "can_transition": request.user.has_perm("production.transition_productionjob"),
        "can_assign_machine": request.user.has_perm("production.assign_productionmachine"),
        "can_assign_machine_now": can_assign_machine_now,
        "can_confirm_print": request.user.has_perm("production.confirm_productionprint"),
        "can_confirm_print_now": job.status in {"in_progress", "ready_to_ship"},
        "is_reprint": print_count > 0,
        "print_count": print_count,
        "assignment_count": assignment_count,
        "transition_count": job.transitions.count(),
        "require_machine_selection": require_machine_selection,
        "sole_active_machine": active_machines[0] if len(active_machines) == 1 else None,
        "show_machine_workspace": bool(
            can_assign_machine_now or job.assigned_machine_id or assignment_count or print_count
        ),
        "active_machines": active_machines,
        "transition_error": transition_error,
        "machine_error": machine_error,
        "print_error": print_error,
        "handover_date_error": handover_date_error,
        "handover_date_label": handover_date_label(order),
        "estimated_handover_date": (
            order.estimated_handover_date.isoformat() if order.estimated_handover_date else ""
        ),
        "estimated_handover_date_display": (
            order.estimated_handover_date.strftime("%d/%m/%Y")
            if order.estimated_handover_date
            else ""
        ),
        "can_update_handover_date": request.user.has_perm("orders.change_order"),
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
