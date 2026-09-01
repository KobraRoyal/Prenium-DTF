from types import SimpleNamespace

import pytest
from apps.portal.order_status_presentation import operational_order_status


def make_order(**overrides):
    values = {
        "status": "submitted",
        "pricing_status": "priced",
        "awaits_client_payment": False,
        "shipping_method_code": "standard",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("order", "expected_key", "expected_label", "expected_tone"),
    [
        (
            make_order(production_job=SimpleNamespace(status="queued")),
            "queued",
            "En file Atelier",
            "is-warning",
        ),
        (
            make_order(production_job=SimpleNamespace(status="in_progress")),
            "in_progress",
            "En production",
            "is-warning",
        ),
        (
            make_order(production_job=SimpleNamespace(status="completed")),
            "completed",
            "Terminée",
            "is-success",
        ),
        (
            make_order(
                production_job=SimpleNamespace(status="ready_to_ship"),
                shipping_method_code="pickup",
            ),
            "ready_for_pickup",
            "Prête au retrait",
            "is-success",
        ),
        (
            make_order(
                production_job=SimpleNamespace(status="completed"),
                shipment=SimpleNamespace(shipped_at=object()),
            ),
            "shipped",
            "Expédiée",
            "is-success",
        ),
    ],
)
def test_operational_order_status_reflects_the_fulfillment_step(
    order, expected_key, expected_label, expected_tone
):
    status = operational_order_status(order)

    assert (status.key, status.label, status.tone) == (
        expected_key,
        expected_label,
        expected_tone,
    )


def test_operational_order_status_prioritizes_customer_blockers():
    awaiting_payment = make_order(
        awaits_client_payment=True,
        production_job=SimpleNamespace(status="queued"),
    )
    pricing_pending = make_order(
        pricing_status="pending",
        production_job=SimpleNamespace(status="in_progress"),
    )
    cancelled = make_order(
        status="cancelled",
        pricing_status="pending",
        awaits_client_payment=True,
        production_job=SimpleNamespace(status="in_progress"),
    )

    assert operational_order_status(awaiting_payment).label == "Paiement à effectuer"
    assert operational_order_status(pricing_pending).label == "Tarif à confirmer"
    assert operational_order_status(cancelled).label == "Annulée"
