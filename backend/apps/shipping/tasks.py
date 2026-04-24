from celery import shared_task

from apps.shipping.services.sendcloud import ShipmentService


@shared_task(name="shipping.sync_stale_shipments_tracking")
def sync_stale_shipments_tracking_task() -> int:
    return ShipmentService().sync_stale_shipments_tracking(limit=50)
