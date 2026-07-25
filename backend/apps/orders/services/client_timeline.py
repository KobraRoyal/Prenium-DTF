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
            "tracking_number": "",
            "tracking_url": "",
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
                        "tracking_number": "",
                        "tracking_url": "",
                    }
                )
        else:
            events.append(
                {
                    "label": status_label(production_job.status),
                    "detail": "",
                    "occurred_at": production_job.created_at,
                    "status_key": production_job.status,
                    "tracking_number": "",
                    "tracking_url": "",
                }
            )

    try:
        shipment = order.shipment
    except ObjectDoesNotExist:
        shipment = None

    if shipment is not None:
        if shipment.created_at and (
            shipment.tracking_number or shipment.status in {"created", "pending"}
        ):
            label_detail = ""
            if shipment.tracking_number and not shipment.shipped_at:
                label_detail = f"N° de suivi : {shipment.tracking_number}"
            events.append(
                {
                    "label": "Préparation d’expédition",
                    "detail": label_detail,
                    "occurred_at": shipment.created_at,
                    "status_key": "ready_to_ship",
                    "tracking_number": shipment.tracking_number if not shipment.shipped_at else "",
                    "tracking_url": shipment.tracking_url if not shipment.shipped_at else "",
                }
            )
        if shipment.shipped_at:
            carrier_message = str(shipment.sendcloud_status_message or "").strip()
            tracking = str(shipment.tracking_number or "").strip()
            detail_parts = []
            if tracking:
                detail_parts.append(f"N° de suivi : {tracking}")
            if carrier_message:
                detail_parts.append(carrier_message)
            events.append(
                {
                    "label": "Commande expédiée",
                    "detail": " · ".join(detail_parts),
                    "occurred_at": shipment.shipped_at,
                    "status_key": "completed",
                    "tracking_number": tracking,
                    "tracking_url": str(shipment.tracking_url or "").strip(),
                }
            )

    events.sort(key=lambda item: item["occurred_at"])
    return events
