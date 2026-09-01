from celery import shared_task

from apps.pod.services.shopify_ingest import ShopifyFulfillmentIngestService


@shared_task(name="pod.ingest_shopify_pod_fulfillment")
def ingest_shopify_pod_fulfillment_task(
    *,
    raw_body: str,
    hmac_header: str,
    shop_domain: str,
    webhook_id: str = "",
) -> dict:
    return ShopifyFulfillmentIngestService().ingest(
        raw_body=raw_body.encode("latin-1"),
        hmac_header=hmac_header,
        shop_domain=shop_domain,
        webhook_id=webhook_id,
    )


@shared_task(name="pod.sync_rip_lot_drive")
def sync_pod_rip_lot_to_drive_task(lot_public_id: str) -> dict:
    from apps.pod.models import PodRipLot
    from apps.pod.services.rip_drive import PodRipDriveSyncService

    lot = PodRipLot.objects.filter(public_id=lot_public_id).first()
    if lot is None:
        return {"ok": False, "error": "lot_missing"}
    return PodRipDriveSyncService().sync_lot(lot=lot)
