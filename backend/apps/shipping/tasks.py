from celery import shared_task
from django.core.exceptions import ValidationError

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.shipping.services.sendcloud import (
    SendcloudWebhookIdentity,
    ShipmentService,
)


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
def process_sendcloud_parcel_status_webhook_task(
    *,
    parcel: dict,
    event_key: str,
    payload_hash: str,
    provider_event_id: str = "",
) -> dict:
    try:
        order, shipment, duplicate = ShipmentService().apply_parcel_status_webhook(
            parcel=parcel,
            event_identity=SendcloudWebhookIdentity(
                event_key=event_key,
                payload_hash=payload_hash,
                provider_event_id=provider_event_id,
            ),
            source="sendcloud_webhook",
        )
    except ValidationError as exc:
        return {
            "matched": False,
            "error": "; ".join(exc.messages)[:255],
        }
    except Exception as exc:
        record_event(
            action="shipping.sendcloud_webhook_processing_failed",
            status=AuditLogEntry.Status.FAILURE,
            message="Sendcloud webhook processing failed.",
            metadata={
                "error_type": type(exc).__name__,
                "provider_event_id": provider_event_id,
                "payload_hash": payload_hash,
                "source": "sendcloud_webhook",
            },
        )
        raise
    if shipment is None:
        return {"matched": False}
    return {
        "matched": True,
        "duplicate": duplicate,
        "order_public_id": str(order.public_id) if order else None,
        "shipment_public_id": str(shipment.public_id),
        "sendcloud_status_code": shipment.sendcloud_status_code,
        "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
    }
