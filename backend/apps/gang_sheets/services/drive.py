from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.core.public_refs import short_public_ref
from apps.gang_sheets.models import GangSheet, GangSheetDriveSync
from apps.uploads.services.drive import (
    GoogleDriveConfigurationError,
    GoogleDriveGateway,
    GoogleDriveSyncError,
)

GANG_SHEET_DRIVE_ROOT_FOLDER_NAME = "Gang Sheets"


class GangSheetDriveSyncRequired(Exception):
    pass


class GangSheetDriveSyncService:
    def __init__(self, *, gateway: GoogleDriveGateway | None = None):
        self.gateway = gateway

    def ensure_sync_record(self, *, sheet: GangSheet) -> GangSheetDriveSync:
        expected_filename = self.build_drive_filename(sheet)
        sync, _created = GangSheetDriveSync.objects.get_or_create(
            customer=sheet.customer,
            gang_sheet=sheet,
            defaults={
                "status": GangSheetDriveSync.Status.PENDING,
                "revision": sheet.revision,
                "drive_filename": expected_filename,
            },
        )
        if sync.revision != sheet.revision or sync.drive_filename != expected_filename:
            sync.status = GangSheetDriveSync.Status.PENDING
            sync.revision = sheet.revision
            sync.drive_filename = expected_filename
            sync.remote_folder_id = ""
            sync.drive_file_id = ""
            sync.sha256 = ""
            sync.last_error = ""
            sync.synced_at = None
            sync.save(
                update_fields=[
                    "status",
                    "revision",
                    "drive_filename",
                    "remote_folder_id",
                    "drive_file_id",
                    "sha256",
                    "last_error",
                    "synced_at",
                    "updated_at",
                ]
            )
        return sync

    def schedule_sync(self, *, sheet: GangSheet, actor=None, source: str) -> GangSheetDriveSync:
        if not sheet.final_file:
            raise GangSheetDriveSyncRequired("Le fichier HD doit être généré avant Drive.")
        sync = self.ensure_sync_record(sheet=sheet)
        if sync.status == GangSheetDriveSync.Status.SYNCED and sync.drive_file_id:
            return sync
        sync.status = GangSheetDriveSync.Status.PENDING
        sync.last_error = ""
        sync.save(update_fields=["status", "last_error", "updated_at"])
        record_event(
            action="gang_sheet.drive_sync_queued",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=sheet,
            metadata={
                "customer_public_id": str(sheet.customer.public_id),
                "gang_sheet_public_id": str(sheet.public_id),
                "drive_sync_public_id": str(sync.public_id),
                "revision": sheet.revision,
                "source": source,
            },
        )
        if settings.GOOGLE_DRIVE_SYNC_ENABLED:
            from apps.gang_sheets.tasks import sync_gang_sheet_to_drive_task

            sync_gang_sheet_to_drive_task.delay(str(sheet.public_id), source=source)
        return sync

    def sync_sheet(self, *, sheet: GangSheet, actor=None, source: str = "system"):
        sync = self.ensure_sync_record(sheet=sheet)
        if (
            sync.status == GangSheetDriveSync.Status.SYNCED
            and sync.drive_file_id
            and sync.revision == sheet.revision
        ):
            return sync

        try:
            gateway = self._get_gateway()
            remote_folder_id = self._ensure_sheet_folder(sheet=sheet, gateway=gateway)
            with sheet.final_file.open("rb") as handle:
                content = handle.read()
            sha256 = hashlib.sha256(content).hexdigest()
            drive_file_id = gateway.upload_file(
                parent_id=remote_folder_id,
                name=sync.drive_filename or self.build_drive_filename(sheet),
                mime_type="application/pdf",
                content=content,
            )
        except (
            GoogleDriveConfigurationError,
            GoogleDriveSyncError,
            OSError,
            KeyError,
            ValueError,
        ) as error:
            return self._mark_failed(
                sync=sync,
                sheet=sheet,
                actor=actor,
                source=source,
                error=error,
            )

        now = timezone.now()
        sync.status = GangSheetDriveSync.Status.SYNCED
        sync.remote_folder_id = remote_folder_id
        sync.drive_file_id = drive_file_id
        sync.sha256 = sha256
        sync.last_error = ""
        sync.last_attempt_at = now
        sync.synced_at = now
        sync.attempt_count += 1
        sync.save(
            update_fields=[
                "status",
                "remote_folder_id",
                "drive_file_id",
                "sha256",
                "last_error",
                "last_attempt_at",
                "synced_at",
                "attempt_count",
                "updated_at",
            ]
        )
        record_event(
            action="gang_sheet.drive_synced",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=sheet,
            metadata={
                "customer_public_id": str(sheet.customer.public_id),
                "gang_sheet_public_id": str(sheet.public_id),
                "drive_sync_public_id": str(sync.public_id),
                "revision": sheet.revision,
                "sha256": sha256,
                "source": source,
            },
        )
        return sync

    def assert_project_outputs_synced(self, *, project) -> None:
        if not settings.GOOGLE_DRIVE_SYNC_ENABLED:
            return
        sheets = list(
            GangSheet.objects.for_project(project)
            .filter(status=GangSheet.Status.VALIDATED)
            .select_related("drive_sync")
        )
        for sheet in sheets:
            if not sheet.final_file:
                continue
            sync = getattr(sheet, "drive_sync", None)
            if (
                sync is None
                or sync.status != GangSheetDriveSync.Status.SYNCED
                or not sync.drive_file_id
                or sync.revision != sheet.revision
            ):
                raise GangSheetDriveSyncRequired(
                    "Le PDF HD est encore en cours de sauvegarde sécurisée sur Google Drive."
                )

    def build_drive_filename(self, sheet: GangSheet) -> str:
        sheet_ref = short_public_ref(sheet.public_id)
        return f"GS-{sheet_ref}-r{sheet.revision}-production.pdf"

    def _ensure_sheet_folder(self, *, sheet: GangSheet, gateway: GoogleDriveGateway) -> str:
        root_id = gateway.ensure_folder(
            parent_id=gateway.root_folder_id,
            name=GANG_SHEET_DRIVE_ROOT_FOLDER_NAME,
        )
        year_id = gateway.ensure_folder(parent_id=root_id, name=sheet.created_at.strftime("%Y"))
        month_id = gateway.ensure_folder(parent_id=year_id, name=sheet.created_at.strftime("%m"))
        customer_id = gateway.ensure_folder(
            parent_id=month_id,
            name=f"C-{short_public_ref(sheet.customer.public_id)}",
        )
        return gateway.ensure_folder(
            parent_id=customer_id,
            name=f"GS-{short_public_ref(sheet.public_id)}",
        )

    def _mark_failed(self, *, sync, sheet, actor, source: str, error: Exception):
        sync.status = GangSheetDriveSync.Status.FAILED
        sync.last_error = str(error)[:255]
        sync.last_attempt_at = timezone.now()
        sync.attempt_count += 1
        sync.save(
            update_fields=[
                "status",
                "last_error",
                "last_attempt_at",
                "attempt_count",
                "updated_at",
            ]
        )
        record_event(
            action="gang_sheet.drive_sync_failed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=sheet,
            status=AuditLogEntry.Status.FAILURE,
            message=sync.last_error,
            metadata={
                "customer_public_id": str(sheet.customer.public_id),
                "gang_sheet_public_id": str(sheet.public_id),
                "drive_sync_public_id": str(sync.public_id),
                "revision": sheet.revision,
                "source": source,
            },
        )
        return sync

    def _get_gateway(self) -> GoogleDriveGateway:
        if self.gateway is None:
            self.gateway = GoogleDriveGateway()
        return self.gateway


def sync_gang_sheet_to_drive(*, sheet_public_id: str, actor=None, source: str = "system"):
    sheet = (
        GangSheet.objects.select_related("customer", "drive_sync")
        .filter(public_id=sheet_public_id)
        .first()
    )
    if sheet is None:
        raise GangSheet.DoesNotExist(f"GangSheet {sheet_public_id} not found.")
    with transaction.atomic():
        locked = GangSheet.objects.select_for_update().select_related("customer").get(pk=sheet.pk)
        return GangSheetDriveSyncService().sync_sheet(
            sheet=locked,
            actor=actor,
            source=source,
        )
