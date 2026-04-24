import pytest
from apps.auditlog.models import AuditLogEntry
from apps.orders.models import Order
from apps.uploads.models import OrderUpload
from apps.uploads.services.inspections import OrderUploadInspectionService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

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


def assert_private_response_denied(response):
    assert response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }


def create_customer_scope(email: str, customer_name: str):
    from apps.customers.models import Customer, CustomerMembership

    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name)
    CustomerMembership.objects.create(customer=customer, user=user)

    client = APIClient()
    assert client.login(email=user.email, password="pass") is True
    return user, customer, client


def create_staff_client(
    *,
    include_upload_permission: bool,
    include_inspection_permission: bool = False,
):
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    if include_upload_permission:
        staff_user.user_permissions.add(Permission.objects.get(codename="view_orderupload"))
    if include_inspection_permission:
        staff_user.user_permissions.add(
            Permission.objects.get(codename="view_orderuploadinspection")
        )

    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True
    return staff_user, client


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


def client_order_file_list_route(customer_public_id, order_public_id):
    return reverse(
        "uploads:client-order-upload-list-create",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
        },
    )


def client_order_file_detail_route(customer_public_id, order_public_id, file_public_id):
    return reverse(
        "uploads:client-order-upload-detail",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


def client_order_file_download_route(customer_public_id, order_public_id, file_public_id):
    return reverse(
        "uploads:client-order-upload-download",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


def client_order_file_control_route(customer_public_id, order_public_id, file_public_id):
    return reverse(
        "uploads:client-order-upload-inspection-detail",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


def staff_order_file_list_route(order_public_id):
    return reverse("uploads:staff-order-upload-list", kwargs={"order_public_id": order_public_id})


def staff_order_file_detail_route(order_public_id, file_public_id):
    return reverse(
        "uploads:staff-order-upload-detail",
        kwargs={
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


def staff_order_file_download_route(order_public_id, file_public_id):
    return reverse(
        "uploads:staff-order-upload-download",
        kwargs={
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


def staff_order_file_control_route(order_public_id, file_public_id):
    return reverse(
        "uploads:staff-order-upload-inspection-detail",
        kwargs={
            "order_public_id": order_public_id,
            "file_public_id": file_public_id,
        },
    )


@pytest.mark.django_db
def test_client_can_upload_and_read_own_order_files(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    route = client_order_file_list_route(customer.public_id, order.public_id)

    upload_response = client.post(route, {"file": build_uploaded_file()}, format="multipart")

    assert upload_response.status_code == status.HTTP_201_CREATED
    upload_payload = upload_response.json()
    assert upload_payload["original_filename"] == "design.pdf"
    assert upload_payload["mime_type"] == "application/pdf"
    assert upload_payload["size_bytes"] == len(b"%PDF-1.4 sample")
    assert "url" not in upload_payload

    detail_response = client.get(
        client_order_file_detail_route(
            customer.public_id,
            order.public_id,
            upload_payload["public_id"],
        )
    )
    list_response = client.get(route)
    download_response = client.get(
        client_order_file_download_route(
            customer.public_id,
            order.public_id,
            upload_payload["public_id"],
        )
    )
    control_response = client.get(
        client_order_file_control_route(
            customer.public_id,
            order.public_id,
            upload_payload["public_id"],
        )
    )

    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["public_id"] == upload_payload["public_id"]
    assert "uploaded_by_public_id" not in detail_response.json()
    assert control_response.status_code == status.HTTP_200_OK
    assert control_response.json()["upload_public_id"] == upload_payload["public_id"]
    assert control_response.json()["status"] == "ok"
    assert "customer" not in control_response.json()
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["customer_public_id"] == str(customer.public_id)
    assert list_response.json()["order_public_id"] == str(order.public_id)
    assert len(list_response.json()["files"]) == 1
    assert download_response.status_code == status.HTTP_200_OK
    assert download_response.has_header("Content-Disposition")
    assert AuditLogEntry.objects.filter(
        action="order_upload.created",
        target_public_id=upload_payload["public_id"],
    ).exists()
    assert AuditLogEntry.objects.filter(
        action="order_upload.downloaded",
        target_public_id=upload_payload["public_id"],
    ).exists()
    assert AuditLogEntry.objects.filter(
        action="order_upload.inspected",
        target_public_id=upload_payload["public_id"],
    ).exists()


@pytest.mark.django_db
def test_client_cannot_upload_or_read_other_customer_files(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user_a, customer_a, client_a = create_customer_scope("client-a@example.com", "Acme A")
    order_a = create_order(customer_a, user_a)
    user_b, customer_b, client_b = create_customer_scope("client-b@example.com", "Acme B")
    order_b = create_order(customer_b, user_b)

    upload_b_response = client_b.post(
        client_order_file_list_route(customer_b.public_id, order_b.public_id),
        {"file": build_uploaded_file(name="b.pdf")},
        format="multipart",
    )
    assert upload_b_response.status_code == status.HTTP_201_CREATED
    upload_b_public_id = upload_b_response.json()["public_id"]

    forbidden_routes = [
        client_order_file_list_route(customer_b.public_id, order_b.public_id),
        client_order_file_detail_route(
            customer_b.public_id,
            order_b.public_id,
            upload_b_public_id,
        ),
        client_order_file_control_route(
            customer_b.public_id,
            order_b.public_id,
            upload_b_public_id,
        ),
        client_order_file_download_route(
            customer_b.public_id,
            order_b.public_id,
            upload_b_public_id,
        ),
    ]
    for route in forbidden_routes:
        response = client_a.get(route)
        assert_private_response_denied(response)

    forbidden_upload = client_a.post(
        client_order_file_list_route(customer_b.public_id, order_b.public_id),
        {"file": build_uploaded_file(name="forbidden.pdf")},
        format="multipart",
    )
    assert_private_response_denied(forbidden_upload)

    not_found_list = client_a.get(
        client_order_file_list_route(customer_a.public_id, order_b.public_id)
    )
    not_found_detail = client_a.get(
        client_order_file_detail_route(
            customer_a.public_id,
            order_a.public_id,
            upload_b_public_id,
        )
    )
    not_found_control = client_a.get(
        client_order_file_control_route(
            customer_a.public_id,
            order_a.public_id,
            upload_b_public_id,
        )
    )
    not_found_download = client_a.get(
        client_order_file_download_route(
            customer_a.public_id,
            order_a.public_id,
            upload_b_public_id,
        )
    )

    assert not_found_list.status_code == status.HTTP_404_NOT_FOUND
    assert not_found_detail.status_code == status.HTTP_404_NOT_FOUND
    assert not_found_control.status_code == status.HTTP_404_NOT_FOUND
    assert not_found_download.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_anonymous_user_is_denied_from_upload_routes(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, _client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    route = client_order_file_list_route(customer.public_id, order.public_id)
    control_route = client_order_file_control_route(
        customer.public_id,
        order.public_id,
        "11111111-1111-1111-1111-111111111111",
    )
    anonymous_client = APIClient()

    for response in (
        anonymous_client.get(route),
        anonymous_client.get(control_route),
        anonymous_client.post(route, {"file": build_uploaded_file()}, format="multipart"),
    ):
        assert_private_response_denied(response)


@pytest.mark.django_db
def test_client_is_denied_from_staff_upload_routes(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload_response = client.post(
        client_order_file_list_route(customer.public_id, order.public_id),
        {"file": build_uploaded_file(name="staff-route.pdf")},
        format="multipart",
    )
    assert upload_response.status_code == status.HTTP_201_CREATED
    upload_public_id = upload_response.json()["public_id"]

    responses = [
        client.get(staff_order_file_list_route(order.public_id)),
        client.get(staff_order_file_detail_route(order.public_id, upload_public_id)),
        client.get(staff_order_file_control_route(order.public_id, upload_public_id)),
        client.get(staff_order_file_download_route(order.public_id, upload_public_id)),
    ]

    for response in responses:
        assert_private_response_denied(response)


@pytest.mark.django_db
def test_staff_without_dedicated_permission_is_denied(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, _client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload_response = _client.post(
        client_order_file_list_route(customer.public_id, order.public_id),
        {"file": build_uploaded_file(name="staff-route.pdf")},
        format="multipart",
    )
    assert upload_response.status_code == status.HTTP_201_CREATED
    upload_public_id = upload_response.json()["public_id"]
    _staff_user, staff_client = create_staff_client(include_upload_permission=False)

    responses = [
        staff_client.get(staff_order_file_list_route(order.public_id)),
        staff_client.get(staff_order_file_detail_route(order.public_id, upload_public_id)),
        staff_client.get(staff_order_file_control_route(order.public_id, upload_public_id)),
        staff_client.get(staff_order_file_download_route(order.public_id, upload_public_id)),
    ]

    for response in responses:
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_without_inspection_permission_is_denied_from_staff_control_route(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload_response = client.post(
        client_order_file_list_route(customer.public_id, order.public_id),
        {"file": build_uploaded_file(name="staff-control.pdf")},
        format="multipart",
    )
    assert upload_response.status_code == status.HTTP_201_CREATED
    upload_public_id = upload_response.json()["public_id"]

    _staff_user, staff_client = create_staff_client(
        include_upload_permission=True,
        include_inspection_permission=False,
    )

    response = staff_client.get(staff_order_file_control_route(order.public_id, upload_public_id))

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_with_dedicated_permission_can_read_staff_upload_routes(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload_response = client.post(
        client_order_file_list_route(customer.public_id, order.public_id),
        {"file": build_uploaded_file(name="staff.pdf")},
        format="multipart",
    )
    assert upload_response.status_code == status.HTTP_201_CREATED
    upload_public_id = upload_response.json()["public_id"]

    _staff_user, staff_client = create_staff_client(
        include_upload_permission=True,
        include_inspection_permission=True,
    )

    list_response = staff_client.get(staff_order_file_list_route(order.public_id))
    detail_response = staff_client.get(
        staff_order_file_detail_route(order.public_id, upload_public_id)
    )
    control_response = staff_client.get(
        staff_order_file_control_route(order.public_id, upload_public_id)
    )
    download_response = staff_client.get(
        staff_order_file_download_route(order.public_id, upload_public_id)
    )

    assert list_response.status_code == status.HTTP_200_OK
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["customer"]["public_id"] == str(customer.public_id)
    assert control_response.status_code == status.HTTP_200_OK
    assert control_response.json()["customer"]["public_id"] == str(customer.public_id)
    assert download_response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_staff_without_inspection_permission_is_denied_on_staff_control_route(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    upload_response = client.post(
        client_order_file_list_route(customer.public_id, order.public_id),
        {"file": build_uploaded_file(name="staff-control.pdf")},
        format="multipart",
    )
    assert upload_response.status_code == status.HTTP_201_CREATED

    _staff_user, staff_client = create_staff_client(
        include_upload_permission=True,
        include_inspection_permission=False,
    )

    response = staff_client.get(
        staff_order_file_control_route(order.public_id, upload_response.json()["public_id"])
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_client_can_read_own_image_control_details(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("image@example.com", "Acme")
    order = create_order(customer, user)
    upload_response = client.post(
        client_order_file_list_route(customer.public_id, order.public_id),
        {
            "file": build_uploaded_file(
                name="design.png",
                content=MINIMAL_PNG_BYTES,
                content_type="image/png",
            )
        },
        format="multipart",
    )

    assert upload_response.status_code == status.HTTP_201_CREATED
    control_response = client.get(
        client_order_file_control_route(
            customer.public_id,
            order.public_id,
            upload_response.json()["public_id"],
        )
    )

    assert control_response.status_code == status.HTTP_200_OK
    assert control_response.json()["status"] == "ok"
    assert control_response.json()["image_width"] == 1
    assert control_response.json()["image_height"] == 1
    assert control_response.json()["metadata"]["image_readable"] is True


@pytest.mark.django_db
def test_client_control_route_returns_error_status_for_unreadable_image(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("broken@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(
        order=order,
        actor=user,
        name="broken.png",
        content=b"not-a-real-png",
        mime_type="image/png",
    )
    OrderUploadInspectionService().inspect_upload(
        order_upload=upload,
        actor=user,
        source="test_suite",
    )

    response = client.get(
        client_order_file_control_route(
            customer.public_id,
            order.public_id,
            upload.public_id,
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "error"
    assert response.json()["summary_message"] == "Image metadata could not be read."


@pytest.mark.django_db
def test_client_control_route_returns_warning_status_for_unexpected_type(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("unknown@example.com", "Acme")
    order = create_order(customer, user)
    upload = create_stored_order_upload(
        order=order,
        actor=user,
        name="archive.bin",
        content=b"\x00\x01\x02\x03",
        mime_type="application/octet-stream",
    )
    OrderUploadInspectionService().inspect_upload(
        order_upload=upload,
        actor=user,
        source="test_suite",
    )

    response = client.get(
        client_order_file_control_route(
            customer.public_id,
            order.public_id,
            upload.public_id,
        )
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "warning"
    assert response.json()["file_kind"] == "unknown"


@pytest.mark.django_db
def test_upload_rejects_disallowed_mime_type(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 1024

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    route = client_order_file_list_route(customer.public_id, order.public_id)

    response = client.post(
        route,
        {
            "file": build_uploaded_file(
                name="notes.txt",
                content=b"plain text",
                content_type="text/plain",
            )
        },
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == ["File type is not allowed."]


@pytest.mark.django_db
def test_upload_rejects_oversized_file(settings):
    settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES = ALLOWED_MIME_TYPES
    settings.ORDER_UPLOAD_MAX_BYTES = 8

    user, customer, client = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, user)
    route = client_order_file_list_route(customer.public_id, order.public_id)

    response = client.post(
        route,
        {"file": build_uploaded_file(content=b"too-large")},
        format="multipart",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == ["File exceeds the maximum allowed size."]
