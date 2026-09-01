from __future__ import annotations

from django.conf import settings
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import PodRipLot
from apps.pod.services.rip_lots import PodRipLotService
from apps.uploads.services.drive import (
    GoogleDriveConfigurationError,
    GoogleDriveGateway,
    GoogleDriveSyncError,
)

POD_RIP_DRIVE_ROOT = "POD_RIP"


class PodRipDriveSyncService:
    def sync_lot(self, *, lot: PodRipLot, actor=None, gateway=None) -> dict:
        if not getattr(settings, "GOOGLE_DRIVE_SYNC_ENABLED", False):
            return {"skipped": True, "reason": "disabled"}
        try:
            client = gateway or GoogleDriveGateway()
            root_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
            pod_root = client.ensure_folder(parent_id=root_id, name=POD_RIP_DRIVE_ROOT)
            lot_folder = client.ensure_folder(parent_id=pod_root, name=lot.code)
            uploaded = 0
            lot_root = PodRipLotService().nas_root() / lot.nas_relative_path
            if lot_root.exists():
                for path in sorted(lot_root.rglob("*")):
                    if not path.is_file():
                        continue
                    parent_id = lot_folder
                    relative = path.relative_to(lot_root)
                    for part in relative.parts[:-1]:
                        parent_id = client.ensure_folder(parent_id=parent_id, name=part)
                    mime = (
                        "application/json" if path.suffix == ".json" else "application/octet-stream"
                    )
                    client.upload_file(
                        parent_id=parent_id,
                        name=path.name,
                        mime_type=mime,
                        content=path.read_bytes(),
                    )
                    uploaded += 1
            lot.drive_folder_id = lot_folder
            lot.drive_file_count = uploaded
            lot.drive_synced_at = timezone.now()
            lot.drive_error = ""
            lot.save(
                update_fields=[
                    "drive_folder_id",
                    "drive_file_count",
                    "drive_synced_at",
                    "drive_error",
                    "updated_at",
                ]
            )
            record_event(
                action="pod.rip.drive_synced",
                actor=actor,
                target=lot,
                metadata={"files": uploaded, "folder": lot_folder},
            )
            return {"skipped": False, "files": uploaded, "folder": lot_folder}
        except (GoogleDriveConfigurationError, GoogleDriveSyncError, OSError) as exc:
            lot.drive_error = str(exc)[:255]
            lot.save(update_fields=["drive_error", "updated_at"])
            record_event(
                action="pod.rip.drive_sync_failed",
                actor=actor,
                target=lot,
                status="failure",
                message=lot.drive_error,
            )
            return {"skipped": False, "ok": False, "error": lot.drive_error}
