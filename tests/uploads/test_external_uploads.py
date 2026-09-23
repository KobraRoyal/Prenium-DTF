from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from apps.b2b_order_projects.services.projects import ProjectDomainError
from apps.b2b_order_projects.services.reorder import B2BOrderReorderService
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.uploads.models import OrderUpload, OrderUploadDriveSync
from apps.uploads.services.assets import AssetService
from apps.uploads.services.drive import OrderUploadDriveSyncService, repair_order_drive_sync
from apps.uploads.services.inspections import OrderUploadInspectionService
from apps.uploads.services.uploads import OrderUploadService
from django.db import IntegrityError, transaction


@pytest.mark.django_db
def test_external_upload_never_uses_local_preview_download_inspection_or_drive():
    customer = Customer.objects.create(name="External")
    order = Order.objects.create(customer=customer)
    upload = OrderUpload.objects.create(
        order=order,
        file="",
        original_filename="Grand visuel",
        mime_type="",
        size_bytes=0,
        external_url="https://files.example.com/a",
    )
    metadata = Mock()
    assert AssetService().prepare_order_upload_preview(order_upload=upload) is None
    assert (
        OrderUploadService().prepare_download(
            order_upload=upload, actor=None, source="test", audience="staff"
        )
        is None
    )
    inspector = OrderUploadInspectionService(metadata_service=metadata)
    assert inspector.ensure_inspection(order_upload=upload, actor=None, source="test") is None
    metadata.extract.assert_not_called()
    drive = OrderUploadDriveSyncService()
    assert drive.ensure_sync_record(order_upload=upload) is None
    assert drive.schedule_upload_sync(order_upload=upload, actor=None, source="test") is None
    assert drive.sync_upload(order_upload=upload) is None
    upload.full_clean()


@pytest.mark.django_db
def test_external_url_cannot_coexist_with_local_file_or_size():
    customer = Customer.objects.create(name="External")
    order = Order.objects.create(customer=customer)
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderUpload.objects.create(
            order=order,
            file="visual.png",
            original_filename="visual.png",
            mime_type="image/png",
            size_bytes=3,
            external_url="https://files.example.com/a",
        )


@pytest.mark.django_db
def test_reorder_rejects_external_upload_before_project_creation(monkeypatch):
    monkeypatch.setattr(
        "apps.b2b_order_projects.services.reorder.b2b_order_projects_enabled_for_customer",
        lambda customer: True,
    )
    customer = Customer.objects.create(name="External")
    order = Order.objects.create(customer=customer)
    OrderUpload.objects.create(
        order=order,
        file="",
        original_filename="Grand visuel",
        mime_type="",
        size_bytes=0,
        external_url="https://files.example.com/a",
    )
    with pytest.raises(ProjectDomainError) as error:
        B2BOrderReorderService().create_reorder_from_order(
            customer=customer, order=order, actor=None, source="test"
        )
    assert error.value.code == "EXTERNAL_FILE_UNAVAILABLE"


@pytest.mark.django_db
def test_repair_order_drive_skips_external_upload_without_file_io(monkeypatch):
    customer = Customer.objects.create(name="External")
    order = Order.objects.create(customer=customer)
    upload = OrderUpload.objects.create(
        order=order,
        file="",
        original_filename="Grand visuel",
        mime_type="",
        size_bytes=0,
        external_url="https://files.example.com/a",
    )
    gateway = Mock()
    folder = SimpleNamespace(
        public_id=None,
        relative_path="Commandes/2026/test",
        order_folder_id="folder-id",
    )
    folder_service = Mock()
    folder_service._get_gateway.return_value = gateway
    folder_service.ensure_order_folder.return_value = folder
    monkeypatch.setattr(
        "apps.uploads.services.drive.OrderDriveFolderService",
        lambda: folder_service,
    )

    result = repair_order_drive_sync(order=order, source="test")

    assert result["uploads"] == []
    assert result["order_folder_id"] == "folder-id"
    folder_service.ensure_order_folder.assert_called_once()
    assert gateway.mock_calls == []
    assert not OrderUploadDriveSync.objects.filter(order_upload=upload).exists()
