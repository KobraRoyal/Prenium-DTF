from celery import shared_task
from django.core.exceptions import ValidationError

from apps.shipping.services.sendcloud import ShipmentService


@shared_task(name="shipping.sync_stale_shipments_tracking")
def sync_stale_shipments_tracking_task() -> int:
    return ShipmentService().sync_stale_shipments_tracking(limit=50)


@shared_task(
    name="shipping.process_sendcloud_parcel_status_webhook",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def process_sendcloud_parcel_status_webhook_task(parcel: dict) -> dict:
    try:
        order, shipment = ShipmentService().apply_parcel_status_webhook(
            parcel=parcel,
            source="sendcloud_webhook",
        )
    except ValidationError as exc:
        return {
            "matched": False,
            "error": "; ".join(exc.messages)[:255],
        }
    if shipment is None:
        return {"matched": False}
    return {
        "matched": True,
        "order_public_id": str(order.public_id) if order else None,
        "shipment_public_id": str(shipment.public_id),
        "sendcloud_status_code": shipment.sendcloud_status_code,
        "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
    }
