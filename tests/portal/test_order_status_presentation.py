from types import SimpleNamespace

import pytest
from apps.portal.order_status_presentation import (
    client_order_status,
    handover_date_label,
    operational_order_status,
)


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


@pytest.mark.parametrize(
    ("order", "expected_key", "expected_label"),
    [
        (make_order(), "submitted", "Commande transmise"),
        (
            make_order(production_job=SimpleNamespace(status="queued")),
            "queued",
            "En préparation",
        ),
        (
            make_order(production_job=SimpleNamespace(status="in_progress")),
            "in_progress",
            "En production",
        ),
        (
            make_order(production_job=SimpleNamespace(status="blocked")),
            "blocked",
            "En attente de vérification",
        ),
        (
            make_order(
                production_job=SimpleNamespace(status="ready_to_ship"),
                shipping_method_code="pickup",
            ),
            "ready_for_pickup",
            "Prête au retrait",
        ),
        (
            make_order(production_job=SimpleNamespace(status="ready_to_ship")),
            "ready_to_ship",
            "Prête à expédier",
        ),
        (
            make_order(
                production_job=SimpleNamespace(status="completed"),
                shipping_method_code="pickup",
            ),
            "picked_up",
            "Retirée",
        ),
        (
            make_order(production_job=SimpleNamespace(status="completed")),
            "production_completed",
            "Préparation terminée",
        ),
        (
            make_order(
                shipment=SimpleNamespace(
                    shipped_at=object(),
                    sendcloud_status_code="IN_TRANSIT",
                )
            ),
            "shipped",
            "Expédiée",
        ),
        (
            make_order(
                shipment=SimpleNamespace(
                    shipped_at=object(),
                    sendcloud_status_code="DELIVERED",
                )
            ),
            "delivered",
            "Livrée",
        ),
    ],
)
def test_client_order_status_uses_the_general_fulfillment_flow(order, expected_key, expected_label):
    status = client_order_status(order)

    assert (status.key, status.label) == (expected_key, expected_label)


def test_client_order_status_keeps_customer_blockers_in_front_of_production():
    awaiting_payment = make_order(
        awaits_client_payment=True,
        production_job=SimpleNamespace(status="in_progress"),
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

    assert client_order_status(awaiting_payment).label == "Paiement à effectuer"
    assert client_order_status(pricing_pending).label == "Tarif à confirmer"
    assert client_order_status(cancelled).label == "Annulée"


def test_handover_date_label_follows_the_selected_shipping_method():
    assert handover_date_label(make_order(shipping_method_code="pickup")) == "Retrait prévu"
    assert handover_date_label(make_order(shipping_method_code="standard")) == "Livraison prévue"
