from __future__ import annotations

import io
import json
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.uploads.models import OrderDriveFolder, OrderUpload, OrderUploadDriveSync

ORDER_DRIVE_ROOT_FOLDER_NAME = "Commandes"
ORDER_DRIVE_SUBFOLDERS = (
    "00_source_client",
    "01_controle",
    "02_production",
    "03_of",
    "04_shipping",
    "05_archive",
)


class GoogleDriveConfigurationError(Exception):
    pass


class GoogleDriveSyncError(Exception):
    pass


@dataclass(frozen=True)
class DriveRemoteFile:
    file_id: str
    name: str


class GoogleDriveGateway:
    folder_mime_type = "application/vnd.google-apps.folder"

    def __init__(self):
        if not settings.GOOGLE_DRIVE_SHARED_DRIVE_ID:
            raise GoogleDriveConfigurationError("GOOGLE_DRIVE_SHARED_DRIVE_ID must be configured.")
        if not settings.GOOGLE_DRIVE_ROOT_FOLDER_ID:
            raise GoogleDriveConfigurationError("GOOGLE_DRIVE_ROOT_FOLDER_ID must be configured.")
        if not settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON:
            raise GoogleDriveConfigurationError(
                "GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON must be configured."
            )

        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as error:
            raise GoogleDriveConfigurationError(
                "Google Drive dependencies are not installed."
            ) from error

        credentials = service_account.Credentials.from_service_account_info(
            json.loads(settings.GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON),
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        self.shared_drive_id = settings.GOOGLE_DRIVE_SHARED_DRIVE_ID
        self.root_folder_id = settings.GOOGLE_DRIVE_ROOT_FOLDER_ID
        self.service = build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def ensure_folder(self, *, parent_id: str, name: str) -> str:
        existing = self._find_item(parent_id=parent_id, name=name, mime_type=self.folder_mime_type)
        if existing is not None:
            return existing.file_id

        try:
            created = (
                self.service.files()
                .create(
                    body={
                        "name": name,
                        "mimeType": self.folder_mime_type,
                        "parents": [parent_id],
                    },
                    fields="id,name",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as error:  # pragma: no cover
            raise GoogleDriveSyncError(f"Unable to create Drive folder '{name}'.") from error
        return created["id"]

    def find_file_by_name(self, *, parent_id: str, name: str) -> DriveRemoteFile | None:
        return self._find_item(parent_id=parent_id, name=name)

    def upload_file(self, *, parent_id: str, name: str, mime_type: str, content: bytes) -> str:
        existing = self.find_file_by_name(parent_id=parent_id, name=name)
        if existing is not None:
            return existing.file_id

        try:
            from googleapiclient.http import MediaIoBaseUpload
        except ImportError as error:
            raise GoogleDriveConfigurationError(
                "Google Drive dependencies are not installed."
            ) from error

        media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
        try:
            created = (
                self.service.files()
                .create(
                    body={"name": name, "parents": [parent_id]},
                    media_body=media,
                    fields="id,name",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as error:  # pragma: no cover
            raise GoogleDriveSyncError(f"Unable to upload Drive file '{name}'.") from error
        return created["id"]

    def _find_item(
        self,
        *,
        parent_id: str,
        name: str,
        mime_type: str | None = None,
    ) -> DriveRemoteFile | None:
        sanitized_name = name.replace("'", "\\'")
        clauses = [
            "trashed = false",
            f"'{parent_id}' in parents",
            f"name = '{sanitized_name}'",
        ]
        if mime_type:
            clauses.append(f"mimeType = '{mime_type}'")

        try:
            response = (
                self.service.files()
                .list(
                    corpora="drive",
                    driveId=self.shared_drive_id,
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    q=" and ".join(clauses),
                    pageSize=1,
                    fields="files(id,name)",
                )
                .execute()
            )
        except Exception as error:  # pragma: no cover
            raise GoogleDriveSyncError("Unable to query Google Drive.") from error

        files = response.get("files", [])
        if not files:
            return None
        item = files[0]
        return DriveRemoteFile(file_id=item["id"], name=item["name"])


class OrderDriveFolderService:
    def __init__(self, gateway: GoogleDriveGateway | None = None):
        self.gateway = gateway

    def ensure_order_folder(self, *, order, actor=None, source: str = "system") -> OrderDriveFolder:
        existing = getattr(order, "drive_folder", None)
        if existing is not None and existing.order_folder_id and existing.folder_ids:
            return existing

        gateway = self._get_gateway()
        commands_folder_id = gateway.ensure_folder(
            parent_id=gateway.root_folder_id,
            name=ORDER_DRIVE_ROOT_FOLDER_NAME,
        )
        year_folder_id = gateway.ensure_folder(
            parent_id=commands_folder_id,
            name=order.created_at.strftime("%Y"),
        )
        month_folder_id = gateway.ensure_folder(
            parent_id=year_folder_id,
            name=order.created_at.strftime("%m"),
        )
        order_folder_id = gateway.ensure_folder(
            parent_id=month_folder_id,
            name=str(order.public_id),
        )

        folder_ids = {}
        for folder_name in ORDER_DRIVE_SUBFOLDERS:
            folder_ids[folder_name] = gateway.ensure_folder(
                parent_id=order_folder_id,
                name=folder_name,
            )

        relative_path = (
            f"{ORDER_DRIVE_ROOT_FOLDER_NAME}/"
            f"{order.created_at.strftime('%Y')}/"
            f"{order.created_at.strftime('%m')}/"
            f"{order.public_id}"
        )
        drive_folder, created = OrderDriveFolder.objects.update_or_create(
            order=order,
            defaults={
                "shared_drive_id": gateway.shared_drive_id,
                "relative_path": relative_path,
                "order_folder_id": order_folder_id,
                "folder_ids": folder_ids,
            },
        )

        if created:
            record_event(
                action="order_drive_folder.created",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=drive_folder,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "relative_path": relative_path,
                    "source": source,
                },
            )
        return drive_folder

    def _get_gateway(self) -> GoogleDriveGateway:
        if self.gateway is None:
            self.gateway = GoogleDriveGateway()
        return self.gateway


class OrderUploadDriveSyncService:
    def __init__(
        self,
        *,
        gateway: GoogleDriveGateway | None = None,
        folder_service: OrderDriveFolderService | None = None,
    ):
        self.gateway = gateway
        self.folder_service = folder_service

    def ensure_sync_record(self, *, order_upload: OrderUpload) -> OrderUploadDriveSync:
        sync, _created = OrderUploadDriveSync.objects.get_or_create(
            order_upload=order_upload,
            defaults={
                "status": OrderUploadDriveSync.Status.PENDING,
                "drive_filename": self.build_drive_filename(order_upload),
            },
        )
        expected_filename = self.build_drive_filename(order_upload)
        if sync.drive_filename != expected_filename:
            sync.drive_filename = expected_filename
            sync.save(update_fields=["drive_filename", "updated_at"])
        return sync

    def schedule_upload_sync(self, *, order_upload: OrderUpload, actor, source: str) -> None:
        sync = self.ensure_sync_record(order_upload=order_upload)
        if sync.status != OrderUploadDriveSync.Status.SYNCED:
            sync.status = OrderUploadDriveSync.Status.PENDING
            sync.last_error = ""
            sync.save(update_fields=["status", "last_error", "updated_at"])

        record_event(
            action="order_upload.drive_sync_queued",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata={
                "order_public_id": str(order_upload.order.public_id),
                "customer_public_id": str(order_upload.order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "drive_sync_public_id": str(sync.public_id),
                "source": source,
            },
        )

        if settings.GOOGLE_DRIVE_SYNC_ENABLED:
            from apps.uploads.tasks import sync_order_upload_to_drive_task

            sync_order_upload_to_drive_task.delay(str(order_upload.public_id), source=source)

    def sync_upload(self, *, order_upload: OrderUpload, actor=None, source: str = "system"):
        sync = self.ensure_sync_record(order_upload=order_upload)
        if sync.status == OrderUploadDriveSync.Status.SYNCED and sync.drive_file_id:
            return sync

        try:
            drive_folder = self._get_folder_service().ensure_order_folder(
                order=order_upload.order,
                actor=actor,
                source=source,
            )
            source_folder_id = drive_folder.folder_ids["00_source_client"]
            with order_upload.file.open("rb") as handle:
                content = handle.read()

            remote_file_id = sync.drive_file_id or self._get_gateway().upload_file(
                parent_id=source_folder_id,
                name=sync.drive_filename or self.build_drive_filename(order_upload),
                mime_type=order_upload.mime_type,
                content=content,
            )
        except (GoogleDriveConfigurationError, GoogleDriveSyncError, OSError, KeyError) as error:
            return self._mark_failed(
                sync=sync,
                order_upload=order_upload,
                actor=actor,
                source=source,
                error=error,
            )

        sync.status = OrderUploadDriveSync.Status.SYNCED
        sync.drive_folder = drive_folder
        sync.remote_folder_id = source_folder_id
        sync.drive_file_id = remote_file_id
        sync.last_error = ""
        sync.last_attempt_at = timezone.now()
        sync.synced_at = sync.last_attempt_at
        sync.attempt_count += 1
        sync.save(
            update_fields=[
                "status",
                "drive_folder",
                "remote_folder_id",
                "drive_file_id",
                "last_error",
                "last_attempt_at",
                "synced_at",
                "attempt_count",
                "updated_at",
            ]
        )

        record_event(
            action="order_upload.drive_synced",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata={
                "order_public_id": str(order_upload.order.public_id),
                "customer_public_id": str(order_upload.order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "drive_sync_public_id": str(sync.public_id),
                "source": source,
            },
        )
        return sync

    def get_staff_sync(self, *, order_upload: OrderUpload) -> OrderUploadDriveSync:
        return self.ensure_sync_record(order_upload=order_upload)

    def get_upload_sync(self, *, order_upload: OrderUpload) -> OrderUploadDriveSync:
        return self.ensure_sync_record(order_upload=order_upload)

    def record_view_event(
        self,
        *,
        order_upload: OrderUpload,
        drive_sync: OrderUploadDriveSync,
        actor,
        source: str,
    ) -> None:
        record_event(
            action="order_upload.drive_sync_viewed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata={
                "order_public_id": str(order_upload.order.public_id),
                "customer_public_id": str(order_upload.order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "drive_sync_public_id": str(drive_sync.public_id),
                "drive_sync_status": drive_sync.status,
                "source": source,
            },
        )

    def build_drive_filename(self, order_upload: OrderUpload) -> str:
        cleaned_name = get_valid_filename(order_upload.original_filename) or "upload"
        return f"{order_upload.public_id}-{cleaned_name}"

    def _mark_failed(self, *, sync, order_upload, actor, source: str, error: Exception):
        sync.status = OrderUploadDriveSync.Status.FAILED
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
            action="order_upload.drive_sync_failed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            status=AuditLogEntry.Status.FAILURE,
            message=sync.last_error,
            metadata={
                "order_public_id": str(order_upload.order.public_id),
                "customer_public_id": str(order_upload.order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "drive_sync_public_id": str(sync.public_id),
                "source": source,
            },
        )
        return sync

    def _get_gateway(self) -> GoogleDriveGateway:
        if self.gateway is None:
            self.gateway = GoogleDriveGateway()
        return self.gateway

    def _get_folder_service(self) -> OrderDriveFolderService:
        if self.folder_service is None:
            self.folder_service = OrderDriveFolderService(gateway=self._get_gateway())
        return self.folder_service


def sync_order_upload_to_drive(*, order_upload_public_id: str, actor=None, source: str = "system"):
    order_upload = (
        OrderUpload.objects.select_related(
            "order",
            "order__customer",
            "order__drive_folder",
            "uploaded_by",
            "drive_sync",
        )
        .filter(public_id=order_upload_public_id)
        .first()
    )
    if order_upload is None:
        raise OrderUpload.DoesNotExist(f"OrderUpload {order_upload_public_id} not found.")

    with transaction.atomic():
        # Verrouiller uniquement uploads_orderupload : avec select_related sur des JOIN
        # nullable (ex. drive_folder), PostgreSQL refuse FOR UPDATE sur la requête complète.
        OrderUpload.objects.select_for_update(of=("self",)).get(pk=order_upload.pk)
        locked_upload = OrderUpload.objects.select_related(
            "order",
            "order__customer",
            "order__drive_folder",
            "uploaded_by",
            "drive_sync",
        ).get(pk=order_upload.pk)
        return OrderUploadDriveSyncService().sync_upload(
            order_upload=locked_upload,
            actor=actor,
            source=source,
        )
