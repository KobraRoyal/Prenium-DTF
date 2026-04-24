import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.uploads.models import OrderUpload
from apps.uploads.services.inspections import OrderUploadInspectionService
from apps.uploads.services.uploads import OrderUploadService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from tests.uploads.mime_fixtures import ORDER_UPLOAD_ALLOWED_MIME_TYPES as ALLOWED_MIME_TYPES

MINIMAL_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00"
    b"\x90wS\xde"
    b"\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfeA\xa6\x1d\xc9"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


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


def create_stored_order_upload(*, order, actor, name, content, mime_type):
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


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_creates_upload_and_audit_entry():
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

    assert upload.order == order
    assert upload.uploaded_by == user
    assert upload.original_filename == "design.pdf"
    assert upload.mime_type == "application/pdf"
    assert upload.size_bytes == len(b"%PDF-1.4 sample")
    assert upload.inspection.status == "ok"
    assert upload.inspection.file_kind == "pdf"
    assert AuditLogEntry.objects.filter(
        action="order_upload.created",
        target_public_id=upload.public_id,
    ).exists()
    assert AuditLogEntry.objects.filter(
        action="order_upload.inspected",
        target_public_id=upload.public_id,
    ).exists()


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_lists_and_gets_customer_scoped_uploads():
    user_a, customer_a, membership_a = create_customer_scope("client-a@example.com", "Acme A")
    order_a = create_order(customer_a, user_a)
    user_b, customer_b, membership_b = create_customer_scope("client-b@example.com", "Acme B")
    order_b = create_order(customer_b, user_b)
    service = OrderUploadService()

    upload_a1 = service.create_upload(
        customer=customer_a,
        actor=user_a,
        customer_membership=membership_a,
        order_public_id=order_a.public_id,
        uploaded_file=build_uploaded_file(name="a-1.pdf"),
        source="client_api",
    )
    upload_a2 = service.create_upload(
        customer=customer_a,
        actor=user_a,
        customer_membership=membership_a,
        order_public_id=order_a.public_id,
        uploaded_file=build_uploaded_file(name="a-2.pdf"),
        source="client_api",
    )
    upload_b = service.create_upload(
        customer=customer_b,
        actor=user_b,
        customer_membership=membership_b,
        order_public_id=order_b.public_id,
        uploaded_file=build_uploaded_file(name="b.pdf"),
        source="client_api",
    )

    scoped_order, uploads = service.list_customer_order_uploads(
        customer=customer_a,
        order_public_id=order_a.public_id,
    )

    assert scoped_order == order_a
    assert {upload.public_id for upload in uploads} == {upload_a1.public_id, upload_a2.public_id}
    assert (
        service.get_customer_order_upload(
            customer=customer_a,
            order_public_id=order_a.public_id,
            upload_public_id=upload_a1.public_id,
        )[1]
        == upload_a1
    )
    assert (
        service.get_customer_order_upload(
            customer=customer_a,
            order_public_id=order_a.public_id,
            upload_public_id=upload_b.public_id,
        )[1]
        is None
    )
    assert (
        service.get_staff_order_upload(
            order_public_id=order_a.public_id,
            upload_public_id=upload_a2.public_id,
        )[1]
        == upload_a2
    )
    assert (
        service.get_staff_order_upload(
            order_public_id=order_a.public_id,
            upload_public_id=upload_b.public_id,
        )[1]
        is None
    )


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_refuses_actor_outside_customer_scope():
    user, customer, _membership = create_customer_scope("client@example.com", "Acme")
    outsider = get_user_model().objects.create_user(email="outsider@example.com", password="pass")
    order = create_order(customer, user)

    with pytest.raises(ValidationError, match="Actor is not allowed for this customer."):
        OrderUploadService().create_upload(
            customer=customer,
            actor=outsider,
            order_public_id=order.public_id,
            uploaded_file=build_uploaded_file(),
            source="client_api",
        )


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_rejects_empty_file():
    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)

    with pytest.raises(ValidationError, match="Empty files are not allowed."):
        OrderUploadService().create_upload(
            customer=customer,
            actor=user,
            customer_membership=membership,
            order_public_id=order.public_id,
            uploaded_file=build_uploaded_file(content=b""),
            source="client_api",
        )


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_rejects_disallowed_mime_type():
    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)

    with pytest.raises(ValidationError, match="File type is not allowed."):
        OrderUploadService().create_upload(
            customer=customer,
            actor=user,
            customer_membership=membership,
            order_public_id=order.public_id,
            uploaded_file=build_uploaded_file(
                name="notes.txt",
                content=b"plain text",
                content_type="text/plain",
            ),
            source="client_api",
        )


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_accepts_octet_stream_ai_as_postscript():
    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload = OrderUploadService().create_upload(
        customer=customer,
        actor=user,
        customer_membership=membership,
        order_public_id=order.public_id,
        uploaded_file=SimpleUploadedFile(
            "logo.ai",
            b"%!PS-Adobe-3.0",
            content_type="application/octet-stream",
        ),
        source="client_api",
    )
    assert upload.mime_type == "application/postscript"


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_rejects_octet_stream_with_disallowed_extension():
    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    with pytest.raises(ValidationError, match="File type is not allowed."):
        OrderUploadService().create_upload(
            customer=customer,
            actor=user,
            customer_membership=membership,
            order_public_id=order.public_id,
            uploaded_file=SimpleUploadedFile(
                "malware.exe",
                b"MZ",
                content_type="application/octet-stream",
            ),
            source="client_api",
        )


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=8,
)
def test_order_upload_service_rejects_oversized_file():
    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)

    with pytest.raises(ValidationError, match="File exceeds the maximum allowed size."):
        OrderUploadService().create_upload(
            customer=customer,
            actor=user,
            customer_membership=membership,
            order_public_id=order.public_id,
            uploaded_file=build_uploaded_file(content=b"too-large"),
            source="client_api",
        )


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_download_records_audit_entry():
    user, customer, membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    service = OrderUploadService()
    upload = service.create_upload(
        customer=customer,
        actor=user,
        customer_membership=membership,
        order_public_id=order.public_id,
        uploaded_file=build_uploaded_file(),
        source="client_api",
    )

    downloaded_upload = service.download_customer_order_upload(
        customer=customer,
        actor=user,
        customer_membership=membership,
        order_public_id=order.public_id,
        upload_public_id=upload.public_id,
        source="client_api",
    )

    assert downloaded_upload == upload
    assert AuditLogEntry.objects.filter(
        action="order_upload.downloaded",
        target_public_id=upload.public_id,
    ).exists()


@pytest.mark.django_db
@override_settings(
    ORDER_UPLOAD_ALLOWED_MIME_TYPES=ALLOWED_MIME_TYPES,
    ORDER_UPLOAD_MAX_BYTES=1024,
)
def test_order_upload_service_extracts_readable_png_metadata():
    user, customer, membership = create_customer_scope("image@example.com", "Acme")
    order = create_order(customer, user)

    upload = OrderUploadService().create_upload(
        customer=customer,
        actor=user,
        customer_membership=membership,
        order_public_id=order.public_id,
        uploaded_file=build_uploaded_file(
            name="design.png",
            content=MINIMAL_PNG_BYTES,
            content_type="image/png",
        ),
        source="client_api",
    )

    assert upload.inspection.status == "ok"
    assert upload.inspection.file_kind == "image"
    assert upload.inspection.image_width == 1
    assert upload.inspection.image_height == 1
    assert upload.inspection.metadata["image_readable"] is True


@pytest.mark.django_db
def test_order_upload_inspection_service_marks_unreadable_image_as_error():
    user, customer, _membership = create_customer_scope("broken@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(
        order=order,
        actor=user,
        name="broken.png",
        content=b"not-a-real-png",
        mime_type="image/png",
    )

    inspection = OrderUploadInspectionService().inspect_upload(
        order_upload=upload,
        actor=user,
        source="test_suite",
    )

    assert inspection.status == "error"
    assert inspection.summary_message == "Image metadata could not be read."
    assert inspection.image_width is None
    assert inspection.image_height is None
    assert inspection.metadata["image_readable"] is False
    assert AuditLogEntry.objects.filter(
        action="order_upload.inspected",
        target_public_id=upload.public_id,
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_order_upload_inspection_service_marks_unexpected_type_as_warning():
    user, customer, _membership = create_customer_scope("other@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(
        order=order,
        actor=user,
        name="archive.bin",
        content=b"\x00\x01\x02\x03",
        mime_type="application/octet-stream",
    )

    inspection = OrderUploadInspectionService().inspect_upload(
        order_upload=upload,
        actor=user,
        source="test_suite",
    )

    assert inspection.status == "warning"
    assert inspection.file_kind == "unknown"
    assert (
        inspection.summary_message
        == "No specialized metadata extractor is available for this file type."
    )
    assert inspection.metadata["file_extension"] == "bin"
