import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.uploads.models import OrderDriveFolder, OrderUpload, OrderUploadDriveSync
from apps.uploads.services.drive import (
    GoogleDriveSyncError,
    OrderUploadDriveSyncService,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.uploads.mime_fixtures import ORDER_UPLOAD_ALLOWED_MIME_TYPES as ALLOWED_MIME_TYPES


def create_customer_scope(email: str, customer_name: str):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name)
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    return user, customer, membership


def create_order(customer, actor):
    return Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="0.00",
        total_amount="0.00",
    )


def create_stored_order_upload(
    *,
    order,
    actor,
    name="design.pdf",
    content=b"%PDF-1.4 sample",
    mime_type="application/pdf",
):
    upload = OrderUpload(
        order=order,
        uploaded_by=actor,
        original_filename=name,
        mime_type=mime_type,
        size_bytes=len(content),
    )
    upload.file.save(name, ContentFile(content), save=False)
    upload.save()
    return upload


def create_staff_client(*, include_sync_permission: bool):
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    if include_sync_permission:
        staff_user.user_permissions.add(
            Permission.objects.get(codename="view_orderuploaddrivesync")
        )

    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True
    return staff_user, client


def staff_order_file_drive_sync_route(order_public_id, file_public_id):
    return reverse(
        "uploads:staff-order-upload-drive-sync-detail",
        kwargs={
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


class FakeDriveGateway:
    def __init__(self, *, fail_upload: bool = False):
        self.fail_upload = fail_upload
        self.shared_drive_id = "shared-drive-id"
        self.root_folder_id = "root-folder-id"
        self.folders = {}
        self.uploads = []

    def ensure_folder(self, *, parent_id: str, name: str) -> str:
        key = (parent_id, name)
        if key not in self.folders:
            self.folders[key] = f"{parent_id}/{name}"
        return self.folders[key]

    def upload_file(
        self,
        *,
        parent_id: str,
        name: str,
        mime_type: str,
        content: bytes,
    ) -> str:
        if self.fail_upload:
            raise GoogleDriveSyncError("Drive API unavailable.")
        self.uploads.append(
            {
                "parent_id": parent_id,
                "name": name,
                "mime_type": mime_type,
                "size": len(content),
            }
        )
        return f"drive-file-{name}"


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_drive_sync_service_creates_order_folder_and_syncs_upload():
    user, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(order=order, actor=user)
    gateway = FakeDriveGateway()
    sync_service = OrderUploadDriveSyncService(gateway=gateway)
    sync = sync_service.sync_upload(order_upload=upload, actor=user, source="test")
    sync_again = sync_service.sync_upload(order_upload=upload, actor=user, source="test")

    assert sync.status == OrderUploadDriveSync.Status.SYNCED
    assert sync.drive_file_id == sync_again.drive_file_id
    assert sync.drive_folder is not None
    assert sync.drive_folder.shared_drive_id == "shared-drive-id"
    assert sync.drive_folder.relative_path.endswith(order.short_ref)
    assert sync.drive_folder.folder_ids["00_source_client"] == sync.remote_folder_id
    assert OrderDriveFolder.objects.filter(order=order).exists()
    assert sync_again.drive_file_id == sync.drive_file_id
    assert len(gateway.uploads) == 1
    assert gateway.uploads[0]["name"] == sync.drive_filename
    assert gateway.uploads[0]["name"].startswith(f"{order.short_ref}-")
    assert str(upload.public_id) not in gateway.uploads[0]["name"].split("-", 1)[0]
    assert AuditLogEntry.objects.filter(
        action="order_upload.drive_synced",
        target_public_id=upload.public_id,
    ).exists()


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_drive_sync_service_uses_single_order_folder_for_multiple_uploads():
    user, customer, _membership = create_customer_scope("multi@example.com", "Acme")
    order = create_order(customer, user)
    first = create_stored_order_upload(order=order, actor=user, name="logo-a.pdf")
    second = create_stored_order_upload(order=order, actor=user, name="logo-b.pdf")
    third = create_stored_order_upload(order=order, actor=user, name="logo-c.pdf")
    gateway = FakeDriveGateway()
    sync_service = OrderUploadDriveSyncService(gateway=gateway)

    syncs = [
        sync_service.sync_upload(order_upload=upload, actor=user, source="test")
        for upload in (first, second, third)
    ]

    assert OrderDriveFolder.objects.filter(order=order).count() == 1
    source_folder_id = syncs[0].drive_folder.folder_ids["00_source_client"]
    assert all(sync.remote_folder_id == source_folder_id for sync in syncs)
    assert all(sync.drive_folder_id == syncs[0].drive_folder_id for sync in syncs)
    assert len(gateway.uploads) == 3
    assert {upload["parent_id"] for upload in gateway.uploads} == {source_folder_id}
    order_folder_names = {
        name for (_parent, name) in gateway.folders if name == order.short_ref
    }
    assert len(order_folder_names) == 1


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_drive_sync_service_marks_failed_when_drive_api_errors():
    user, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(order=order, actor=user)
    sync = OrderUploadDriveSyncService(
        gateway=FakeDriveGateway(fail_upload=True),
    ).sync_upload(order_upload=upload, actor=user, source="test")

    assert sync.status == OrderUploadDriveSync.Status.FAILED
    assert sync.last_error == "Drive API unavailable."
    assert sync.drive_file_id == ""
    assert AuditLogEntry.objects.filter(
        action="order_upload.drive_sync_failed",
        target_public_id=upload.public_id,
    ).exists()


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_build_drive_filename_uses_order_short_ref_and_disambiguates_duplicates():
    user, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    first = create_stored_order_upload(order=order, actor=user, name="logo.png")
    second = create_stored_order_upload(order=order, actor=user, name="logo.png")
    service = OrderUploadDriveSyncService(gateway=FakeDriveGateway())

    first_name = service.build_drive_filename(first)
    second_name = service.build_drive_filename(second)

    assert first_name == f"{order.short_ref}-logo.png"
    assert second_name.startswith(f"{order.short_ref}-logo-")
    assert second_name.endswith(".png")
    assert first_name != second_name


@pytest.mark.django_db
def test_client_routes_do_not_expose_drive_sync_details(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(order=order, actor=user)
    OrderUploadDriveSync.objects.create(
        order_upload=upload,
        status=OrderUploadDriveSync.Status.SYNCED,
        drive_filename=f"{upload.public_id}-design.pdf",
        remote_folder_id="drive-folder-id",
        drive_file_id="drive-file-id",
    )

    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    detail_response = client.get(
        reverse(
            "uploads:client-order-upload-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
                "file_public_id": upload.public_id,
            },
        )
    )
    control_response = client.get(
        reverse(
            "uploads:client-order-upload-inspection-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "order_public_id": order.public_id,
                "file_public_id": upload.public_id,
            },
        )
    )

    assert detail_response.status_code == status.HTTP_200_OK
    assert "drive_sync" not in detail_response.json()
    assert "drive_file_id" not in detail_response.content.decode()
    assert control_response.status_code == status.HTTP_200_OK
    assert "drive_file_id" not in control_response.content.decode()
    assert membership.customer == customer


@pytest.mark.django_db
def test_staff_drive_sync_route_requires_dedicated_permission(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(order=order, actor=user)
    OrderUploadDriveSync.objects.create(order_upload=upload)

    _staff_user, client = create_staff_client(include_sync_permission=False)
    response = client.get(staff_order_file_drive_sync_route(order.public_id, upload.public_id))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_with_dedicated_permission_can_view_drive_sync_status(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(order=order, actor=user)
    sync = OrderUploadDriveSync.objects.create(
        order_upload=upload,
        status=OrderUploadDriveSync.Status.FAILED,
        last_error="Drive API unavailable.",
    )

    _staff_user, client = create_staff_client(include_sync_permission=True)
    response = client.get(staff_order_file_drive_sync_route(order.public_id, upload.public_id))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["public_id"] == str(sync.public_id)
    assert payload["status"] == OrderUploadDriveSync.Status.FAILED
    assert payload["last_error"] == "Drive API unavailable."
    assert "drive_file_id" not in payload
    assert "remote_folder_id" not in payload
    assert AuditLogEntry.objects.filter(
        action="order_upload.drive_sync_viewed",
        target_public_id=upload.public_id,
    ).exists()
