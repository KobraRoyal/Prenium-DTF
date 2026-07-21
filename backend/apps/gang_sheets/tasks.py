from celery import shared_task

from apps.gang_sheets.services.rendering import GangSheetRenderService


@shared_task(
    bind=True,
    name="gang_sheets.render",
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 2},
)
def render_gang_sheet_task(self, sheet_public_id: str):
    sheet = GangSheetRenderService().render(sheet_public_id=sheet_public_id)
    return {"public_id": str(sheet.public_id), "status": sheet.status}


@shared_task(name="gang_sheets.sync_to_google_drive")
def sync_gang_sheet_to_drive_task(sheet_public_id: str, source: str = "system"):
    from apps.gang_sheets.services.drive import sync_gang_sheet_to_drive

    sync = sync_gang_sheet_to_drive(sheet_public_id=sheet_public_id, source=source)
    return sync.status
