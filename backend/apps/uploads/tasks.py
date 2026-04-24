from celery import shared_task

from apps.uploads.services.drive import sync_order_upload_to_drive


@shared_task(name="uploads.sync_order_upload_to_drive_task")
def sync_order_upload_to_drive_task(order_upload_public_id: str, source: str = "system"):
    sync = sync_order_upload_to_drive(
        order_upload_public_id=order_upload_public_id,
        source=source,
    )
    return sync.status
