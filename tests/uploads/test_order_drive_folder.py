import pytest
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.uploads.models import OrderDriveFolder, OrderUpload, OrderUploadDriveSync
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile


@pytest.mark.django_db
def test_google_drive_folder_url():
    user = get_user_model().objects.create_user(email="d@example.com", password="pass")
    customer = Customer.objects.create(name="C")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    folder = OrderDriveFolder.objects.create(
        order=order,
        shared_drive_id="sd",
        relative_path="x",
        order_folder_id="folderABC",
        folder_ids={},
    )
    assert folder.google_drive_folder_url() == "https://drive.google.com/drive/folders/folderABC"


@pytest.mark.django_db
def test_google_drive_folder_url_empty_id():
    user = get_user_model().objects.create_user(email="d2@example.com", password="pass")
    customer = Customer.objects.create(name="C2")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    folder = OrderDriveFolder(
        order=order,
        shared_drive_id="sd",
        relative_path="x",
        order_folder_id="",
        folder_ids={},
    )
    folder.save()
    assert folder.google_drive_folder_url() is None


@pytest.mark.django_db
def test_upload_drive_sync_google_drive_browser_url_prefers_file():
    user = get_user_model().objects.create_user(email="f@example.com", password="pass")
    customer = Customer.objects.create(name="Cf")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="x.png",
        mime_type="image/png",
        size_bytes=4,
    )
    upload.file.save("x.png", ContentFile(b"x"), save=True)
    df = OrderDriveFolder.objects.create(
        order=order,
        shared_drive_id="sd",
        relative_path="p",
        order_folder_id="ofold",
        folder_ids={},
    )
    sync = OrderUploadDriveSync.objects.create(
        order_upload=upload,
        drive_folder=df,
        status=OrderUploadDriveSync.Status.SYNCED,
        drive_file_id="fileXYZ",
        remote_folder_id="subfold",
    )
    assert sync.google_drive_browser_url() == "https://drive.google.com/file/d/fileXYZ/view"


@pytest.mark.django_db
def test_upload_drive_sync_google_drive_browser_url_falls_back_to_folder():
    user = get_user_model().objects.create_user(email="f2@example.com", password="pass")
    customer = Customer.objects.create(name="Cf2")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        currency="EUR",
        subtotal_amount="0",
        total_amount="0",
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="y.png",
        mime_type="image/png",
        size_bytes=4,
    )
    upload.file.save("y.png", ContentFile(b"x"), save=True)
    df = OrderDriveFolder.objects.create(
        order=order,
        shared_drive_id="sd",
        relative_path="p",
        order_folder_id="ofold",
        folder_ids={},
    )
    sync = OrderUploadDriveSync.objects.create(
        order_upload=upload,
        drive_folder=df,
        status=OrderUploadDriveSync.Status.PENDING,
        drive_file_id="",
        remote_folder_id="remoteF",
    )
    assert sync.google_drive_browser_url() == "https://drive.google.com/drive/folders/remoteF"
