from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import PodDriveHdSource, ShopifyWebhookReceipt
from apps.pod.services.shopify_ingest import ShopifyFulfillmentIngestService
from apps.pod.services.validation import validation_message

_DRIVE_HD_RECOVERY_LOCK_SECONDS = 30 * 60


@shared_task(
    bind=True,
    name="pod.import_drive_hd_source",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=20,
    default_retry_delay=60,
)
def import_pod_drive_hd_source_task(self, source_public_id: str) -> dict:
    from apps.pod.services.drive_hd_sources import DriveHdSourceService

    result = DriveHdSourceService().import_source(source_public_id=source_public_id)
    if result.get("status") == "importing":
        raise self.retry(exc=RuntimeError("Drive HD import is still in progress."))
    if not result.get("ok") and result.get("error") != "source_missing":
        raise self.retry(exc=RuntimeError("Drive HD import failed."))
    return result


@shared_task(name="pod.recover_drive_hd_sources")
def recover_pod_drive_hd_sources_task(limit: int = 100) -> dict:
    """Republish imports lost before Celery accepted them or after a worker died."""
    now = timezone.now()
    sources = list(
        PodDriveHdSource.objects.filter(recipe_slots__isnull=False)
        .filter(
            Q(
                status=PodDriveHdSource.Status.PENDING,
                updated_at__lte=now - timedelta(minutes=2),
            )
            | Q(
                status=PodDriveHdSource.Status.IMPORTING,
                updated_at__lte=now - timedelta(minutes=16),
            )
        )
        .order_by("updated_at")
        .distinct()
        .values_list("public_id", flat=True)[: min(max(int(limit), 1), 100)]
    )
    dispatched = 0
    for source_public_id in sources:
        lock_key = f"pod:drive_hd_recovery:{source_public_id}"
        try:
            if not cache.add(lock_key, "queued", timeout=_DRIVE_HD_RECOVERY_LOCK_SECONDS):
                continue
            import_pod_drive_hd_source_task.delay(str(source_public_id))
        except Exception as exc:
            cache.delete(lock_key)
            record_event(
                action="pod.drive_hd_source.recovery_dispatch_failed",
                status="failure",
                message="La reprise de l'import Drive HD sera retentée au prochain passage.",
                metadata={"error_type": type(exc).__name__},
            )
            break
        dispatched += 1
    return {"due": len(sources), "dispatched": dispatched}


@shared_task(name="pod.ingest_shopify_pod_fulfillment")
def ingest_shopify_pod_fulfillment_task(
    *,
    raw_body: str,
    hmac_header: str,
    shop_domain: str,
    webhook_id: str = "",
    topic: str = "orders/create",
) -> dict:
    return ShopifyFulfillmentIngestService().ingest(
        raw_body=raw_body.encode("latin-1"),
        hmac_header=hmac_header,
        shop_domain=shop_domain,
        webhook_id=webhook_id,
        topic=topic,
    )


@shared_task(name="pod.process_shopify_pod_inbox")
def process_shopify_pod_inbox_task(receipt_public_id: str) -> dict:
    try:
        result = ShopifyFulfillmentIngestService().process_receipt(
            receipt_public_id=receipt_public_id
        )
        return {"ok": True, **result}
    except Exception as exc:
        with transaction.atomic():
            receipt = (
                ShopifyWebhookReceipt.objects.select_for_update()
                .filter(public_id=receipt_public_id)
                .first()
            )
            if receipt is not None and receipt.status != ShopifyWebhookReceipt.Status.PROCESSED:
                receipt.attempts += 1
                receipt.status = ShopifyWebhookReceipt.Status.FAILED
                receipt.next_retry_at = timezone.now() + timedelta(
                    seconds=min(60 * 2 ** min(receipt.attempts, 6), 3600)
                )
                receipt.last_error = (
                    validation_message(exc)[:500]
                    if isinstance(exc, ValidationError)
                    else type(exc).__name__
                )
                receipt.save(
                    update_fields=[
                        "attempts",
                        "status",
                        "next_retry_at",
                        "last_error",
                        "updated_at",
                    ]
                )
        record_event(
            action="pod.shopify.webhook_processing_failed",
            status="failure",
            message="Livraison Shopify conservée dans l'inbox pour rejeu.",
            metadata={"receipt_public_id": receipt_public_id, "error_type": type(exc).__name__},
        )
        return {"ok": False, "retryable": True}


@shared_task(name="pod.recover_shopify_pod_inbox")
def recover_shopify_pod_inbox_task(limit: int = 100) -> dict:
    now = timezone.now()
    receipts = list(
        ShopifyWebhookReceipt.objects.filter(
            status__in=[
                ShopifyWebhookReceipt.Status.PENDING,
                ShopifyWebhookReceipt.Status.FAILED,
            ]
        )
        .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
        .order_by("created_at")
        .values_list("public_id", flat=True)[: min(max(int(limit), 1), 100)]
    )
    dispatched = 0
    for receipt_public_id in receipts:
        try:
            process_shopify_pod_inbox_task.delay(str(receipt_public_id))
        except Exception:
            break
        dispatched += 1
    return {"due": len(receipts), "dispatched": dispatched}


@shared_task(
    bind=True,
    name="pod.prepare_pick_session_rip_and_drive",
    acks_late=True,
    reject_on_worker_lost=True,
    max_retries=5,
    default_retry_delay=90,
)
def prepare_pick_session_rip_and_drive_task(
    self,
    *,
    session_public_id: str,
    actor_id: int | None = None,
) -> dict:
    from apps.accounts.models import User
    from apps.pod.models import PodPickSession
    from apps.pod.services.rip_lots import PodRipLotService

    session = PodPickSession.objects.filter(public_id=session_public_id).first()
    if session is None:
        return {"ok": False, "error": "session_missing"}
    actor = User.objects.filter(pk=actor_id).first() if actor_id else None
    if actor is None:
        return {"ok": False, "error": "actor_missing"}
    try:
        lot = PodRipLotService().prepare_dtf_for_pick_session(
            actor=actor,
            session=session,
            source="pod.pick.session_opened",
        )
    except ValidationError as exc:
        message = validation_message(exc)
        record_event(
            action="pod.pick.session_rip_auto_failed",
            actor=actor,
            target=session,
            status="failure",
            message=message,
            metadata={"session_code": session.code},
        )
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        return {"ok": False, "error": message}
    if lot is None:
        return {"ok": False, "error": "nothing_to_prepare"}
    return {"ok": True, "lot_public_id": str(lot.public_id), "session_code": session.code}


@shared_task(name="pod.sync_rip_lot_drive")
def sync_pod_rip_lot_to_drive_task(lot_public_id: str) -> dict:
    from apps.pod.models import PodRipLot
    from apps.pod.services.rip_drive import PodRipDriveSyncService

    lot = PodRipLot.objects.filter(public_id=lot_public_id).first()
    if lot is None:
        return {"ok": False, "error": "lot_missing"}
    return PodRipDriveSyncService().sync_lot(lot=lot)
