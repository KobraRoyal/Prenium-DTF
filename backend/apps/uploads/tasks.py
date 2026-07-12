from celery import shared_task

from apps.uploads.services.drive import sync_order_upload_to_drive


@shared_task(name="uploads.sync_order_upload_to_drive_task")
def sync_order_upload_to_drive_task(order_upload_public_id: str, source: str = "system"):
    sync = sync_order_upload_to_drive(
        order_upload_public_id=order_upload_public_id,
        source=source,
    )
    return sync.status


@shared_task(name="uploads.analyze_asset_version")
def analyze_asset_version_task(asset_version_public_id: str):
    from apps.uploads.services.asset_analysis import AssetAnalysisService

    version = AssetAnalysisService().analyze(version_public_id=asset_version_public_id)
    return version.analysis_status if version is not None else None
