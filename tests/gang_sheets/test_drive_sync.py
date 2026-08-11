import hashlib

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.gang_sheets.models import GangSheet, GangSheetDriveSync, GangSheetSourceAsset
from apps.gang_sheets.services import GangSheetDriveSyncRequired, GangSheetService
from apps.gang_sheets.services.drive import GangSheetDriveSyncService
from apps.uploads.services.drive import GoogleDriveSyncError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from .helpers import attach_png_asset, create_customer_scope

pytestmark = pytest.mark.django_db


class FakeDriveGateway:
    def __init__(self, *, fail_upload=False):
        self.fail_upload = fail_upload
        self.shared_drive_id = "shared-drive-id"
        self.root_folder_id = "root-folder-id"
        self.folders = {}
        self.uploads = []
        self.file_meta = {}
        self.trashed_ids = set()
        self._seq = 0

    def ensure_folder(self, *, parent_id, name):
        key = (parent_id, name)
        existing = self.folders.get(key)
        if existing and existing not in self.trashed_ids:
            return existing
        self._seq += 1
        folder_id = f"{parent_id}/{name}#{self._seq}"
        self.folders[key] = folder_id
        self.file_meta[folder_id] = {
            "id": folder_id,
            "name": name,
            "trashed": False,
            "mimeType": "application/vnd.google-apps.folder",
        }
        return folder_id

    def get_file_metadata(self, file_id):
        if not file_id:
            return None
        if file_id in self.trashed_ids:
            meta = dict(self.file_meta.get(file_id) or {"id": file_id, "name": file_id})
            meta["trashed"] = True
            meta.setdefault("mimeType", "application/vnd.google-apps.folder")
            return meta
        return self.file_meta.get(file_id)

    def is_active_folder(self, file_id):
        meta = self.get_file_metadata(file_id)
        if meta is None or meta.get("trashed"):
            return False
        return meta.get("mimeType") == "application/vnd.google-apps.folder"

    def upload_file(self, *, parent_id, name, mime_type, content):
        if self.fail_upload:
            raise GoogleDriveSyncError("Drive API unavailable.")
        self.uploads.append(
            {
                "parent_id": parent_id,
                "name": name,
                "mime_type": mime_type,
                "content": content,
            }
        )
        file_id = f"drive-file-{name}"
        self.file_meta[file_id] = {
            "id": file_id,
            "name": name,
            "trashed": False,
            "mimeType": mime_type,
        }
        return file_id


def create_hd_sheet(*, email="gang-drive@example.com", project=None):
    user, customer, default_project = create_customer_scope(email=email)
    sheet = GangSheetService().create_sheet(
        customer=customer if project is None else None,
        project=project,
        actor=user,
        name="Planche Drive",
    )
    content = b"%PDF-1.4\n% private gang sheet HD\n%%EOF\n"
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        content,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])
    return user, customer, default_project, sheet, content


def test_drive_sync_uploads_exact_hd_bytes_and_is_idempotent():
    user, customer, _project, sheet, content = create_hd_sheet()
    gateway = FakeDriveGateway()
    service = GangSheetDriveSyncService(gateway=gateway)

    sync = service.sync_sheet(sheet=sheet, actor=user, source="test")
    same_sync = service.sync_sheet(sheet=sheet, actor=user, source="test")

    assert sync == same_sync
    assert sync.customer == customer
    assert sync.status == GangSheetDriveSync.Status.SYNCED
    assert sync.revision == sheet.revision
    assert sync.sha256 == hashlib.sha256(content).hexdigest()
    assert sync.drive_file_id.startswith("drive-file-GS-")
    assert len(gateway.uploads) == 1
    assert gateway.uploads[0]["content"] == content
    assert gateway.uploads[0]["mime_type"] == "application/pdf"
    assert "/01_Production" in gateway.uploads[0]["parent_id"]
    assert "Gang Sheets" in gateway.uploads[0]["parent_id"]
    assert GangSheetDriveSync.objects.for_customer(customer).get() == sync
    assert AuditLogEntry.objects.filter(
        action="gang_sheet.drive_synced",
        target_public_id=sheet.public_id,
    ).exists()


def test_drive_sync_uploads_source_assets_and_pdf_into_order_folders():
    from apps.orders.models import Order
    from apps.uploads.models import OrderDriveFolder

    user, customer, _project, sheet, content = create_hd_sheet(email="gang-drive-order@example.com")
    asset, version = attach_png_asset(customer=customer, project=_project, user=user)
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
    )
    sheet.order = order
    sheet.save(update_fields=["order", "updated_at"])

    gateway = FakeDriveGateway()
    sync = GangSheetDriveSyncService(gateway=gateway).sync_sheet(
        sheet=sheet, actor=user, source="test.order"
    )

    assert sync.status == GangSheetDriveSync.Status.SYNCED
    assert OrderDriveFolder.objects.filter(order=order).exists()
    folder_ids = order.drive_folder.folder_ids
    assert set(folder_ids) >= {"00_source_Client", "01_Production"}
    assert len(gateway.uploads) == 2
    parents = {item["parent_id"] for item in gateway.uploads}
    assert folder_ids["00_source_Client"] in parents
    assert folder_ids["01_Production"] in parents
    pdf_upload = next(item for item in gateway.uploads if item["mime_type"] == "application/pdf")
    assert pdf_upload["content"] == content
    assert pdf_upload["parent_id"] == folder_ids["01_Production"]
    source_upload = next(item for item in gateway.uploads if item["mime_type"] != "application/pdf")
    assert source_upload["parent_id"] == folder_ids["00_source_Client"]
    assert "src-" in source_upload["name"]
    assert version.original_filename in source_upload["name"] or "logo" in source_upload["name"]


def test_drive_sync_failure_is_tracked_and_audited():
    user, _customer, _project, sheet, _content = create_hd_sheet(
        email="gang-drive-failure@example.com"
    )

    sync = GangSheetDriveSyncService(gateway=FakeDriveGateway(fail_upload=True)).sync_sheet(
        sheet=sheet, actor=user, source="test"
    )

    assert sync.status == GangSheetDriveSync.Status.FAILED
    assert sync.last_error == "Drive API unavailable."
    assert sync.drive_file_id == ""
    assert sync.attempt_count == 1
    assert AuditLogEntry.objects.filter(
        action="gang_sheet.drive_sync_failed",
        target_public_id=sheet.public_id,
    ).exists()


@override_settings(GOOGLE_DRIVE_SYNC_ENABLED=True)
def test_drive_sync_schedule_queues_the_async_task(monkeypatch):
    user, _customer, _project, sheet, _content = create_hd_sheet(
        email="gang-drive-queue@example.com"
    )
    queued = []
    monkeypatch.setattr(
        "apps.gang_sheets.tasks.sync_gang_sheet_to_drive_task.delay",
        lambda sheet_public_id, source: queued.append((sheet_public_id, source)),
    )

    sync = GangSheetDriveSyncService().schedule_sync(
        sheet=sheet,
        actor=user,
        source="test.queue",
    )

    assert sync.status == GangSheetDriveSync.Status.PENDING
    assert queued == [(str(sheet.public_id), "test.queue")]
    assert AuditLogEntry.objects.filter(
        action="gang_sheet.drive_sync_queued",
        target_public_id=sheet.public_id,
    ).exists()


def test_new_revision_resets_the_remote_file_reference():
    user, _customer, _project, sheet, _content = create_hd_sheet(
        email="gang-drive-revision@example.com"
    )
    service = GangSheetDriveSyncService(gateway=FakeDriveGateway())
    sync = service.sync_sheet(sheet=sheet, actor=user, source="test")
    old_filename = sync.drive_filename
    sheet.revision += 1
    sheet.save(update_fields=["revision", "updated_at"])

    reset_sync = service.ensure_sync_record(sheet=sheet)

    assert reset_sync.status == GangSheetDriveSync.Status.PENDING
    assert reset_sync.revision == sheet.revision
    assert reset_sync.drive_file_id == ""
    assert reset_sync.sha256 == ""
    assert reset_sync.drive_filename != old_filename


def test_validation_schedules_drive_storage_before_order(
    django_capture_on_commit_callbacks,
):
    user, customer, project = create_customer_scope(email="gang-drive-validation@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="À valider")
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    service = GangSheetService()
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)
    sheet.refresh_from_db()
    sheet.status = GangSheet.Status.READY
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    class RecordingDriveSync:
        calls = []

        def schedule_sync(self, *, sheet, actor, source):
            self.calls.append((sheet.public_id, actor.id, source))

    drive_sync = RecordingDriveSync()
    with django_capture_on_commit_callbacks(execute=True):
        GangSheetService(drive_sync=drive_sync).validate_sheet(sheet=sheet, actor=user)

    assert drive_sync.calls == [(sheet.public_id, user.id, "client_portal.validation")]


@override_settings(GOOGLE_DRIVE_SYNC_ENABLED=True)
def test_checkout_guard_requires_current_drive_revision():
    _user, _customer, project, sheet, _content = create_hd_sheet(
        email="gang-drive-guard@example.com"
    )
    sheet.project = project
    sheet.save(update_fields=["project", "updated_at"])
    service = GangSheetDriveSyncService()
    sync = service.ensure_sync_record(sheet=sheet)

    with pytest.raises(GangSheetDriveSyncRequired):
        service.assert_project_outputs_synced(project=project)

    sync.status = GangSheetDriveSync.Status.SYNCED
    sync.drive_file_id = "drive-file-id"
    sync.save(update_fields=["status", "drive_file_id", "updated_at"])
    service.assert_project_outputs_synced(project=project)

    sync.revision = sheet.revision - 1
    sync.save(update_fields=["revision", "updated_at"])
    with pytest.raises(GangSheetDriveSyncRequired):
        service.assert_project_outputs_synced(project=project)


def test_client_editor_never_exposes_google_drive_identifiers(client):
    user, _customer, _project, sheet, _content = create_hd_sheet(
        email="gang-drive-private@example.com"
    )
    GangSheetDriveSync.objects.create(
        customer=sheet.customer,
        gang_sheet=sheet,
        status=GangSheetDriveSync.Status.SYNCED,
        revision=sheet.revision,
        remote_folder_id="secret-drive-folder-id",
        drive_file_id="secret-drive-file-id",
    )
    client.force_login(user)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": sheet.customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert response.status_code == 200
    assert b"secret-drive-folder-id" not in response.content
    assert b"secret-drive-file-id" not in response.content


@override_settings(GOOGLE_DRIVE_SYNC_ENABLED=True)
def test_sync_gang_sheet_to_drive_locks_sheet_without_nullable_order_join(monkeypatch):
    """Régression : SELECT FOR UPDATE + select_related(order) casse sous PostgreSQL."""
    from apps.gang_sheets.services import drive as drive_module

    user, _customer, _project, sheet, content = create_hd_sheet(email="gang-drive-lock@example.com")
    assert sheet.order_id is None
    gateway = FakeDriveGateway()

    monkeypatch.setattr(
        drive_module.GangSheetDriveSyncService,
        "_get_gateway",
        lambda self: gateway,
    )

    sync = drive_module.sync_gang_sheet_to_drive(
        sheet_public_id=str(sheet.public_id),
        actor=user,
        source="test.lock",
    )

    assert sync.status == GangSheetDriveSync.Status.SYNCED
    assert sync.sha256 == hashlib.sha256(content).hexdigest()
    assert len(gateway.uploads) == 1


def test_order_project_detail_shows_drive_sync_message_not_visuals_fallback():
    from pathlib import Path

    from django.conf import settings

    template = (
        Path(settings.BASE_DIR) / "templates/portal/client/order_project_detail.html"
    ).read_text(encoding="utf-8")
    assert 'submit_error == "gang_sheet_drive_sync_required"' in template
    assert "sauvegarde sécurisée du PDF HD" in template
    drive_branch = template.split('submit_error == "gang_sheet_drive_sync_required"', 1)[1]
    assert "Complétez et validez tous les visuels" not in drive_branch.split("{% elif", 1)[0]
