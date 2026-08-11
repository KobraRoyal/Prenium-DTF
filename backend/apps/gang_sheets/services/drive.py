from __future__ import annotations

import hashlib

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.core.public_refs import short_public_ref
from apps.gang_sheets.models import GangSheet, GangSheetDriveSync, GangSheetSourceAsset
from apps.uploads.services.drive import (
    ORDER_DRIVE_PRODUCTION_FOLDER,
    ORDER_DRIVE_PRODUCTION_FOLDER_ALIASES,
    ORDER_DRIVE_SOURCE_FOLDER,
    ORDER_DRIVE_SOURCE_FOLDER_ALIASES,
    GoogleDriveConfigurationError,
    GoogleDriveGateway,
    GoogleDriveSyncError,
    OrderDriveFolderService,
    resolve_order_drive_subfolder_id,
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

    def force_resync(
        self,
        *,
        sheet: GangSheet,
        actor=None,
        source: str,
        queue: bool = True,
    ) -> GangSheetDriveSync:
        """Réinitialise le sync (ex. après rattachement commande) puis refile la tâche."""
        sync = self.ensure_sync_record(sheet=sheet)
        sync.status = GangSheetDriveSync.Status.PENDING
        sync.remote_folder_id = ""
        sync.drive_file_id = ""
        sync.sha256 = ""
        sync.last_error = ""
        sync.synced_at = None
        sync.save(
            update_fields=[
                "status",
                "remote_folder_id",
                "drive_file_id",
                "sha256",
                "last_error",
                "synced_at",
                "updated_at",
            ]
        )
        if queue:
            return self.schedule_sync(sheet=sheet, actor=actor, source=source)
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
            folders = self._resolve_destination_folders(sheet=sheet, gateway=gateway, actor=actor)
            source_count = self._sync_source_assets(
                sheet=sheet,
                gateway=gateway,
                source_folder_id=folders["source_folder_id"],
            )
            with sheet.final_file.open("rb") as handle:
                content = handle.read()
            sha256 = hashlib.sha256(content).hexdigest()
            drive_file_id = gateway.upload_file(
                parent_id=folders["production_folder_id"],
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
        sync.remote_folder_id = folders["production_folder_id"]
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
                "destination": folders["destination"],
                "source_asset_count": source_count,
                "order_public_id": (
                    str(sheet.order.public_id) if getattr(sheet, "order_id", None) else None
                ),
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

    def build_source_drive_filename(
        self, *, sheet: GangSheet, asset, original_filename: str
    ) -> str:
        sheet_ref = short_public_ref(sheet.public_id)
        asset_ref = short_public_ref(asset.public_id)
        cleaned = get_valid_filename(original_filename) or "source"
        return f"GS-{sheet_ref}-src-{asset_ref}-{cleaned}"

    def _resolve_destination_folders(self, *, sheet: GangSheet, gateway: GoogleDriveGateway, actor):
        """Commande liée → ``Commandes/…`` ; sinon staging ``Gang Sheets/…``."""
        if sheet.order_id:
            drive_folder = OrderDriveFolderService(gateway=gateway).ensure_order_folder(
                order=sheet.order,
                actor=actor,
                source="gang_sheet.drive_sync",
            )
            return {
                "destination": "order",
                "source_folder_id": resolve_order_drive_subfolder_id(
                    drive_folder.folder_ids,
                    *ORDER_DRIVE_SOURCE_FOLDER_ALIASES,
                ),
                "production_folder_id": resolve_order_drive_subfolder_id(
                    drive_folder.folder_ids,
                    *ORDER_DRIVE_PRODUCTION_FOLDER_ALIASES,
                ),
            }

        sheet_folder_id = self._ensure_sheet_folder(sheet=sheet, gateway=gateway)
        return {
            "destination": "gang_sheet_staging",
            "source_folder_id": gateway.ensure_folder(
                parent_id=sheet_folder_id,
                name=ORDER_DRIVE_SOURCE_FOLDER,
            ),
            "production_folder_id": gateway.ensure_folder(
                parent_id=sheet_folder_id,
                name=ORDER_DRIVE_PRODUCTION_FOLDER,
            ),
        }

    def _sync_source_assets(
        self,
        *,
        sheet: GangSheet,
        gateway: GoogleDriveGateway,
        source_folder_id: str,
    ) -> int:
        entries = list(
            GangSheetSourceAsset.objects.for_sheet(sheet)
            .select_related("asset", "asset__current_version")
            .order_by("sort_order", "created_at")
        )
        uploaded = 0
        for entry in entries:
            version = entry.asset.current_version if entry.asset_id else None
            if version is None or not version.file:
                continue
            filename = self.build_source_drive_filename(
                sheet=sheet,
                asset=entry.asset,
                original_filename=version.original_filename or entry.asset.name,
            )
            with version.file.open("rb") as handle:
                content = handle.read()
            gateway.upload_file(
                parent_id=source_folder_id,
                name=filename,
                mime_type=version.mime_type or "application/octet-stream",
                content=content,
            )
            uploaded += 1
        return uploaded

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
        GangSheet.objects.select_related("customer", "order", "drive_sync")
        .filter(public_id=sheet_public_id)
        .first()
    )
    if sheet is None:
        raise GangSheet.DoesNotExist(f"GangSheet {sheet_public_id} not found.")
    with transaction.atomic():
        # Ne pas select_related les FK nullables (order, drive_sync) sous
        # SELECT FOR UPDATE : PostgreSQL refuse FOR UPDATE sur un OUTER JOIN.
        locked = GangSheet.objects.select_for_update().select_related("customer").get(pk=sheet.pk)
        return GangSheetDriveSyncService().sync_sheet(
            sheet=locked,
            actor=actor,
            source=source,
        )
