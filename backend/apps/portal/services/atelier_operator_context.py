from __future__ import annotations

import uuid

from apps.portal.views_staff_production import production_panel_context
from apps.portal.views_staff_reviews import _inspection_context
from apps.production.models import ProductionJob


def _step_state(*, done: bool, blocked: bool = False, active: bool = False) -> str:
    if blocked:
        return "blocked"
    if done:
        return "done"
    if active:
        return "active"
    return "pending"


def build_operator_steps(
    *,
    order,
    job: ProductionJob,
    inspection: dict,
    production: dict,
    shipment=None,
) -> list[dict[str, str]]:
    uploads = inspection.get("uploads") or []
    control_required = bool(uploads)
    control_done = not control_required or inspection.get("all_uploads_approved")
    control_blocked = inspection.get("changes_requested_count", 0) > 0
    control_active = control_required and not control_done and not control_blocked

    machine_done = bool(job.assigned_machine_id)
    machine_active = control_done and not machine_done and production.get("can_assign_machine_now")

    print_done = production.get("print_count", 0) > 0
    production_active = (
        control_done
        and machine_done
        and job.status
        in {
            ProductionJob.Status.QUEUED,
            ProductionJob.Status.IN_PROGRESS,
            ProductionJob.Status.BLOCKED,
        }
    )

    shipping_active = job.status == ProductionJob.Status.READY_TO_SHIP and shipment is None
    shipping_done = job.status == ProductionJob.Status.COMPLETED or shipment is not None

    steps: list[dict[str, str]] = []

    if control_required:
        steps.append(
            {
                "key": "control",
                "label": "Contrôle",
                "state": _step_state(
                    done=control_done,
                    blocked=control_blocked,
                    active=control_active,
                ),
            }
        )

    if order.uses_atelier_pricing():
        meterage_done = order.meterage_override_linear_m is not None
        steps.append(
            {
                "key": "meterage",
                "label": "Métrage",
                "state": _step_state(
                    done=meterage_done,
                    active=control_done and not meterage_done,
                ),
            }
        )

    steps.append(
        {
            "key": "machine",
            "label": "Machine",
            "state": _step_state(
                done=machine_done,
                active=bool(machine_active),
            ),
        }
    )

    steps.append(
        {
            "key": "production",
            "label": "Impression",
            "state": _step_state(
                done=print_done,
                active=production_active and not print_done,
            ),
        }
    )

    steps.append(
        {
            "key": "shipping",
            "label": "Expédition",
            "state": _step_state(
                done=shipping_done,
                active=shipping_active and not shipping_done,
            ),
        }
    )

    if job.status == ProductionJob.Status.COMPLETED:
        steps.append({"key": "completed", "label": "Terminé", "state": "done"})

    return steps


def active_operator_step(steps: list[dict[str, str]]) -> str:
    for step in steps:
        if step["state"] in {"active", "blocked"}:
            return step["key"]
    for step in reversed(steps):
        if step["state"] == "done":
            return step["key"]
    return steps[0]["key"] if steps else "control"


def build_operator_context(
    request,
    *,
    row: dict,
    machine_error: str = "",
    print_error: str = "",
    meterage_error: str = "",
    inspection_error: str = "",
    inspection_error_upload_id: str = "",
) -> dict[str, object]:
    order = row["order"]
    job = row["job"]
    production = production_panel_context(
        request=request,
        order=order,
        job=job,
        machine_error=machine_error,
        print_error=print_error,
    )
    inspection = _inspection_context(
        request,
        order=order,
        form_error=inspection_error,
        error_upload_id=inspection_error_upload_id,
    )
    steps = build_operator_steps(
        order=order,
        job=job,
        inspection=inspection,
        production=production,
        shipment=row.get("shipment"),
    )
    meterage = {
        key: production[key]
        for key in (
            "can_set_meterage_override",
            "order_billable_sqm_preview",
            "dtf_laize_cm",
        )
        if key in production
    }
    return {
        **production,
        **inspection,
        **meterage,
        "operator_steps": steps,
        "operator_active_step": active_operator_step(steps),
        "meterage_hx_target": "#atelier-operations-panel",
        "meterage_form_error": meterage_error,
        "print_request_token": uuid.uuid4(),
        "operations_panel_target": "#atelier-operations-panel",
    }
