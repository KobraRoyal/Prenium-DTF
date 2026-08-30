from types import SimpleNamespace

from apps.portal.services.atelier_operator_context import (
    active_operator_step,
    build_operator_steps,
)
from apps.production.models import ProductionJob


def _order(*, meterage=None, atelier=True):
    return SimpleNamespace(
        meterage_override_linear_m=meterage,
        uses_atelier_pricing=lambda: atelier,
    )


def _job(*, assigned=None, status=ProductionJob.Status.QUEUED):
    return SimpleNamespace(assigned_machine_id=assigned, status=status)


def _inspection(*, approved=True, blocked=False, uploads=True, of_document_issued=True):
    return {
        "uploads": [object()] if uploads else [],
        "all_uploads_approved": approved,
        "changes_requested_count": 1 if blocked else 0,
        "of_document_issued": of_document_issued,
    }


def _production(*, require_machine=True, print_count=0, can_assign=True):
    return {
        "require_machine_selection": require_machine,
        "can_assign_machine_now": can_assign,
        "print_count": print_count,
    }


def test_workflow_order_is_control_machine_meterage_print_shipping():
    steps = build_operator_steps(
        order=_order(),
        job=_job(),
        inspection=_inspection(),
        production=_production(),
    )
    assert [step["key"] for step in steps] == [
        "control",
        "machine",
        "meterage",
        "production",
        "shipping",
    ]
    assert active_operator_step(steps) == "machine"


def test_machine_step_is_skipped_when_a_single_printer_is_available():
    steps = build_operator_steps(
        order=_order(),
        job=_job(),
        inspection=_inspection(),
        production=_production(require_machine=False),
    )
    assert [step["key"] for step in steps] == [
        "control",
        "meterage",
        "production",
        "shipping",
    ]
    assert active_operator_step(steps) == "meterage"


def test_control_stays_first_when_files_are_pending():
    steps = build_operator_steps(
        order=_order(),
        job=_job(),
        inspection=_inspection(approved=False),
        production=_production(),
    )
    assert active_operator_step(steps) == "control"
    assert steps[0]["label"] == "Contrôle fichier"


def test_control_is_blocked_until_of_document_is_issued():
    steps = build_operator_steps(
        order=_order(),
        job=_job(),
        inspection=_inspection(approved=False, of_document_issued=False),
        production=_production(),
    )

    assert active_operator_step(steps) == "control"
    assert steps[0]["state"] == "blocked"
    assert all(step["state"] == "pending" for step in steps[1:])
