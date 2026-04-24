from types import SimpleNamespace

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.uploads.models import normalize_original_filename
from apps.uploads.services.uploads import OrderUploadService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

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


def build_uploaded_file(
    *,
    name: str = "design.pdf",
    content: bytes = b"%PDF-1.4 sample",
    content_type: str = "application/pdf",
):
    return SimpleUploadedFile(name, content, content_type=content_type)


@pytest.mark.django_db
def test_original_filename_is_normalized_and_storage_path_stays_scoped(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)

    upload = OrderUploadService().create_upload(
        customer=customer,
        actor=user,
        customer_membership=membership,
        order_public_id=order.public_id,
        uploaded_file=build_uploaded_file(name="../client assets/Artwork Final.pdf"),
        source="client_api",
    )

    assert normalize_original_filename(r"..\..\report.pdf") == "report.pdf"
    assert normalize_original_filename("") == "upload"
    assert upload.original_filename == "Artwork_Final.pdf"
    assert upload.file.name.startswith(f"orders/{order.public_id}/{upload.public_id}-")
    assert upload.file.name.endswith("Artwork_Final.pdf")
    assert ".." not in upload.file.name
    assert "\\" not in upload.file.name


@pytest.mark.django_db
def test_order_upload_audit_metadata_is_scoped_and_pathless(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)

    upload = OrderUploadService().create_upload(
        customer=customer,
        actor=user,
        customer_membership=membership,
        order_public_id=order.public_id,
        uploaded_file=build_uploaded_file(),
        source="client_api",
    )

    audit_entry = AuditLogEntry.objects.get(
        action="order_upload.created",
        target_public_id=upload.public_id,
    )

    assert audit_entry.metadata == {
        "order_public_id": str(order.public_id),
        "customer_public_id": str(customer.public_id),
        "order_upload_public_id": str(upload.public_id),
        "customer_membership_public_id": str(membership.public_id),
        "mime_type": "application/pdf",
        "size_bytes": len(b"%PDF-1.4 sample"),
        "source": "client_api",
    }
    assert "file_path" not in audit_entry.metadata
    assert "url" not in audit_entry.metadata
    assert "stored_file_name" not in audit_entry.metadata


@pytest.mark.django_db
def test_order_upload_service_rejects_file_without_mime_type(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)

    unreadable_upload = SimpleNamespace(name="scan.bin", size=4, content_type="")

    with pytest.raises(ValidationError, match="A valid MIME type is required."):
        OrderUploadService().create_upload(
            customer=customer,
            actor=user,
            customer_membership=membership,
            order_public_id=order.public_id,
            uploaded_file=unreadable_upload,
            source="client_api",
        )
