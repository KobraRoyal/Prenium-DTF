from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist

from apps.portal.views_common import status_label


def build_client_order_status_history(order) -> list[dict[str, object]]:
    events: list[dict[str, object]] = [
        {
            "label": "Commande transmise",
            "detail": "",
            "occurred_at": order.created_at,
            "status_key": "submitted",
        }
    ]

    try:
        production_job = order.production_job
    except ObjectDoesNotExist:
        production_job = None

    if production_job is not None:
        transitions = list(production_job.transitions.order_by("created_at", "id"))
        if transitions:
            for transition in transitions:
                events.append(
                    {
                        "label": status_label(transition.to_status),
                        "detail": str(transition.reason or "").strip(),
                        "occurred_at": transition.created_at,
                        "status_key": transition.to_status,
                    }
                )
        else:
            events.append(
                {
                    "label": status_label(production_job.status),
                    "detail": "",
                    "occurred_at": production_job.created_at,
                    "status_key": production_job.status,
                }
            )

    events.sort(key=lambda item: item["occurred_at"])
    return events
