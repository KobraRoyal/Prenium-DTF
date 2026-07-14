from io import BytesIO

import pymupdf
import pytest
from apps.auditlog.models import AuditLogEntry
from apps.core.public_refs import short_public_ref
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob, ProductionJobScanLog, ProductionJobTransition
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import (
    OrderUpload,
    OrderUploadDriveSync,
    OrderUploadInspection,
    OrderUploadReview,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient


def assert_private_response_denied(response):
    assert response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }


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
        customer_note="Urgent sample",
    )


def create_stored_order_upload(
    *,
    order,
    actor,
    name="design.pdf",
    content=b"%PDF-1.4 sample",
    mime_type="application/pdf",
    width_mm=None,
    height_mm=None,
    support_color_hex="",
):
    upload = OrderUpload(
        order=order,
        uploaded_by=actor,
        original_filename=name,
        mime_type=mime_type,
        size_bytes=len(content),
        width_mm=width_mm,
        height_mm=height_mm,
        support_color_hex=support_color_hex,
    )
    upload.file.save(name, ContentFile(content), save=False)
    upload.save()
    return upload


def create_staff_client(*, permission_codenames: list[str]):
    staff_user = get_user_model().objects.create_user(
        email=f"staff-{'-'.join(permission_codenames) or 'none'}@example.com",
        password="pass",
        is_staff=True,
    )
    permissions = [Permission.objects.get(codename="access_staff_portal")]
    permissions.extend(
        Permission.objects.get(codename=codename) for codename in permission_codenames
    )
    staff_user.user_permissions.add(*permissions)

    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True
    return staff_user, client


def production_detail_route(order_public_id):
    return reverse(
        "production:staff-production-job-detail",
        kwargs={"order_public_id": order_public_id},
    )


def production_manufacturing_order_pdf_route(order_public_id):
    return reverse(
        "production:staff-manufacturing-order-pdf",
        kwargs={"order_public_id": order_public_id},
    )


def production_transition_route(order_public_id):
    return reverse(
        "production:staff-production-job-transition",
        kwargs={"order_public_id": order_public_id},
    )


def production_scan_resolve_route():
    return reverse("production:staff-production-job-scan-resolve")


def production_scan_transition_route():
    return reverse("production:staff-production-job-scan-transition")


@pytest.mark.django_db
def test_staff_with_permission_can_view_workflow_snapshot():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    upload = create_stored_order_upload(
        order=order,
        actor=actor,
        width_mm="120.00",
        height_mm="80.00",
        support_color_hex="#112233",
    )
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        summary_message="File ready.",
        file_kind="pdf",
        file_extension="pdf",
    )
    OrderUploadDriveSync.objects.create(
        order_upload=upload,
        status=OrderUploadDriveSync.Status.SYNCED,
        drive_filename="masked.pdf",
    )
    OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.APPROVED,
    )
    _staff_user, client = create_staff_client(permission_codenames=["view_productionjob"])

    response = client.get(production_detail_route(order.public_id))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["order_public_id"] == str(order.public_id)
    assert payload["status"] == ProductionJob.Status.QUEUED
    assert payload["scan"]["identifier"] == payload["manufacturing_order"]["number"]
    assert payload["scan"]["identifier"].startswith("OF-")
    assert payload["manufacturing_order"]["scan"]["barcode"]["format"] == "code128"
    assert payload["manufacturing_order"]["document_type"] == "manufacturing_order_v1"
    assert (
        payload["manufacturing_order"]["uploads"][0]["inspection_status"]
        == OrderUploadInspection.Status.OK
    )
    assert (
        payload["manufacturing_order"]["uploads"][0]["drive_sync_status"]
        == OrderUploadDriveSync.Status.SYNCED
    )
    assert (
        payload["manufacturing_order"]["uploads"][0]["atelier_review_status"]
        == OrderUploadReview.Status.APPROVED
    )
    assert payload["manufacturing_order"]["uploads"][0]["dimensions_label"] == "120 × 80 mm"
    assert payload["manufacturing_order"]["uploads"][0]["support_color_label"] == "#112233"
    assert payload["manufacturing_order"]["file_review_summary"] == {
        "total": 1,
        "approved": 1,
        "pending": 0,
        "changes_requested": 0,
        "ready_for_production": True,
    }
    assert "drive_file_id" not in str(payload)
    assert "remote_folder_id" not in str(payload)


@pytest.mark.django_db
def test_staff_can_download_manufacturing_order_pdf():
    actor, customer, _membership = create_customer_scope("pdf@example.com", "Acme PDF")
    order = create_order(customer, actor)
    upload = create_stored_order_upload(
        order=order,
        actor=actor,
        width_mm="120.00",
        height_mm="80.00",
        support_color_hex="#112233",
    )
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        summary_message="Diagnostic technique conforme.",
        file_kind="pdf",
        file_extension="pdf",
    )
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    _staff_user, client = create_staff_client(permission_codenames=["view_productionjob"])

    response = client.get(production_manufacturing_order_pdf_route(order.public_id))

    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"
    with pymupdf.open(stream=response.content, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)

    assert "ORDRE DE FABRICATION" in text
    assert job.manufacturing_order_number in text
    assert f"#{short_public_ref(order.public_id).upper()}" in text
    assert text.count("design.pdf") == 1
    assert "À contrôler" in text
    assert "TAILLE DEMANDÉE" in text
    assert "120 × 80 mm" in text
    assert "COULEUR DU SUPPORT" in text
    assert "#112233" in text
    assert "Total TTC" not in text
    assert "Sync Drive" not in text
    assert "Aperçu\nindisponible" in text


@pytest.mark.django_db
def test_manufacturing_order_pdf_embeds_visual_preview():
    actor, customer, _membership = create_customer_scope("preview@example.com", "Acme Preview")
    order = create_order(customer, actor)
    image_buffer = BytesIO()
    Image.new("RGBA", (640, 320), (249, 115, 22, 210)).save(image_buffer, format="PNG")
    upload = create_stored_order_upload(
        order=order,
        actor=actor,
        name="logo-client.png",
        content=image_buffer.getvalue(),
        mime_type="image/png",
    )
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        summary_message="Visuel conforme.",
        file_kind="image",
        file_extension="png",
    )
    OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.APPROVED,
        reviewed_by=actor,
    )
    ProductionWorkflowService().get_or_create_for_order(order=order)
    _staff_user, client = create_staff_client(permission_codenames=["view_productionjob"])

    response = client.get(production_manufacturing_order_pdf_route(order.public_id))

    assert response.status_code == status.HTTP_200_OK
    with pymupdf.open(stream=response.content, filetype="pdf") as document:
        text = "\n".join(page.get_text() for page in document)
        embedded_images = sum(len(page.get_images(full=True)) for page in document)
    assert embedded_images >= 1
    assert "logo-client.png" in text
    assert "Aperçu\nindisponible" not in text


@pytest.mark.django_db
def test_staff_can_resolve_scan_to_correct_production_job():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order_one = create_order(customer, actor)
    order_two = create_order(customer, actor)
    service = ProductionWorkflowService()
    service.get_or_create_for_order(order=order_one)
    job_two = service.get_or_create_for_order(order=order_two)
    _staff_user, client = create_staff_client(
        permission_codenames=["view_productionjob", "scan_productionjob"]
    )

    response = client.post(
        production_scan_resolve_route(),
        {"scan_identifier": job_two.scan_identifier},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["public_id"] == str(job_two.public_id)
    assert payload["order_public_id"] == str(order_two.public_id)
    assert payload["status"] == ProductionJob.Status.QUEUED
    assert payload["manufacturing_order"]["number"] == job_two.manufacturing_order_number
    assert payload["manufacturing_order"]["scan"]["identifier"] == job_two.scan_identifier
    assert payload["manufacturing_order"]["scan"]["barcode"]["format"] == "code128"
    assert payload["recent_scan_logs"][0]["action"] == ProductionJobScanLog.Action.RESOLVE
    assert ProductionJobScanLog.objects.filter(
        scan_identifier=job_two.scan_identifier,
        action=ProductionJobScanLog.Action.RESOLVE,
        outcome=ProductionJobScanLog.Outcome.RESOLVED,
    ).exists()


@pytest.mark.django_db
def test_invalid_scan_is_refused_on_resolution_route():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    create_order(customer, actor)
    _staff_user, client = create_staff_client(
        permission_codenames=["view_productionjob", "scan_productionjob"]
    )

    response = client.post(
        production_scan_resolve_route(),
        {"scan_identifier": "INVALID-SCAN-CODE"},
        format="json",
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert ProductionJobScanLog.objects.filter(
        scan_identifier="INVALID-SCAN-CODE",
        action=ProductionJobScanLog.Action.RESOLVE,
        outcome=ProductionJobScanLog.Outcome.NOT_FOUND,
    ).exists()


@pytest.mark.django_db
def test_client_is_refused_on_scan_routes():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    client = APIClient()
    assert client.login(email=actor.email, password="pass") is True

    resolve_response = client.post(
        production_scan_resolve_route(),
        {"scan_identifier": job.scan_identifier},
        format="json",
    )
    transition_response = client.post(
        production_scan_transition_route(),
        {
            "scan_identifier": job.scan_identifier,
            "to_status": ProductionJob.Status.IN_PROGRESS,
        },
        format="json",
    )

    assert_private_response_denied(resolve_response)
    assert_private_response_denied(transition_response)


@pytest.mark.django_db
def test_staff_without_scan_read_permission_is_refused():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    _staff_user, client = create_staff_client(permission_codenames=["view_productionjob"])

    response = client.post(
        production_scan_resolve_route(),
        {"scan_identifier": job.scan_identifier},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_without_scan_transition_permission_is_refused():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    _staff_user, client = create_staff_client(
        permission_codenames=["view_productionjob", "transition_productionjob"]
    )

    response = client.post(
        production_scan_transition_route(),
        {
            "scan_identifier": job.scan_identifier,
            "to_status": ProductionJob.Status.IN_PROGRESS,
            "reason": "Start line",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_with_permissions_can_transition_by_scan():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    staff_user, client = create_staff_client(
        permission_codenames=[
            "view_productionjob",
            "transition_productionjob",
            "scan_transition_productionjob",
        ]
    )

    response = client.post(
        production_scan_transition_route(),
        {
            "scan_identifier": job.scan_identifier,
            "to_status": ProductionJob.Status.IN_PROGRESS,
            "reason": "Start line",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["status"] == ProductionJob.Status.IN_PROGRESS
    assert payload["history"][0]["from_status"] == ProductionJob.Status.QUEUED
    assert payload["history"][0]["to_status"] == ProductionJob.Status.IN_PROGRESS
    assert payload["history"][0]["source"] == "staff_scan_api"
    assert payload["history"][0]["changed_by"]["email"] == staff_user.email
    assert ProductionJobTransition.objects.filter(
        production_job__order=order,
        to_status=ProductionJob.Status.IN_PROGRESS,
        source="staff_scan_api",
    ).exists()
    assert ProductionJobScanLog.objects.filter(
        scan_identifier=job.scan_identifier,
        action=ProductionJobScanLog.Action.TRANSITION,
        outcome=ProductionJobScanLog.Outcome.TRANSITIONED,
    ).exists()


@pytest.mark.django_db
def test_invalid_transition_by_scan_is_refused():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    _staff_user, client = create_staff_client(
        permission_codenames=[
            "view_productionjob",
            "transition_productionjob",
            "scan_transition_productionjob",
        ]
    )

    response = client.post(
        production_scan_transition_route(),
        {
            "scan_identifier": job.scan_identifier,
            "to_status": ProductionJob.Status.COMPLETED,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert ProductionJobTransition.objects.filter(production_job__order=order).count() == 0
    assert ProductionJobScanLog.objects.filter(
        scan_identifier=job.scan_identifier,
        action=ProductionJobScanLog.Action.TRANSITION,
        outcome=ProductionJobScanLog.Outcome.REJECTED,
    ).exists()


@pytest.mark.django_db
def test_staff_without_dedicated_read_permission_is_refused():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    _staff_user, client = create_staff_client(permission_codenames=[])

    response = client.get(production_detail_route(order.public_id))
    pdf_response = client.get(production_manufacturing_order_pdf_route(order.public_id))

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert pdf_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_client_is_refused_on_staff_production_routes():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    client = APIClient()
    assert client.login(email=actor.email, password="pass") is True

    response = client.get(production_detail_route(order.public_id))

    assert_private_response_denied(response)


@pytest.mark.django_db
def test_staff_without_transition_permission_is_refused():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    _staff_user, client = create_staff_client(permission_codenames=["view_productionjob"])

    response = client.post(
        production_transition_route(order.public_id),
        {"to_status": ProductionJob.Status.IN_PROGRESS, "reason": "Start line"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_with_transition_permission_can_transition_workflow():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    staff_user, client = create_staff_client(
        permission_codenames=["view_productionjob", "transition_productionjob"]
    )

    response = client.post(
        production_transition_route(order.public_id),
        {"to_status": ProductionJob.Status.IN_PROGRESS, "reason": "Start line"},
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["status"] == ProductionJob.Status.IN_PROGRESS
    assert payload["history"][0]["from_status"] == ProductionJob.Status.QUEUED
    assert payload["history"][0]["to_status"] == ProductionJob.Status.IN_PROGRESS
    assert payload["history"][0]["changed_by"]["email"] == staff_user.email
    assert ProductionJobTransition.objects.filter(
        production_job__order=order,
        to_status=ProductionJob.Status.IN_PROGRESS,
    ).exists()
    assert AuditLogEntry.objects.filter(
        action="production.status_changed",
        target_model="ProductionJob",
    ).exists()


@pytest.mark.django_db
def test_invalid_transition_is_refused_by_staff_transition_route():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    _staff_user, client = create_staff_client(
        permission_codenames=["view_productionjob", "transition_productionjob"]
    )

    response = client.post(
        production_transition_route(order.public_id),
        {"to_status": ProductionJob.Status.COMPLETED},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert ProductionJobTransition.objects.filter(production_job__order=order).count() == 0
    assert AuditLogEntry.objects.filter(
        action="production.transition_rejected",
        target_model="ProductionJob",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()
