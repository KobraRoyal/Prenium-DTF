import json

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUpload, OrderUploadInspection, OrderUploadReview
from apps.uploads.services.reviews import (
    OrderUploadReviewService,
    OrderUploadReviewTargetNotFound,
)
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone


def _staff(*codenames: str):
    user = get_user_model().objects.create_user(
        email=f"atelier-{get_user_model().objects.count()}@example.com",
        password="pass",
        is_staff=True,
    )
    requested = ["access_staff_portal", *codenames]
    user.user_permissions.set(Permission.objects.filter(codename__in=requested))
    return user


def _order_with_upload(
    *,
    customer_name: str = "Client A",
    support_color="#112233",
    of_document_issued: bool = True,
):
    customer = Customer.objects.create(name=customer_name, billing_email="client@example.com")
    order = Order.objects.create(customer=customer, status=Order.Status.SUBMITTED)
    production_job = ProductionWorkflowService().get_or_create_for_order(order=order)
    if of_document_issued:
        production_job.of_document_issued_at = timezone.now()
        production_job.save(update_fields=["of_document_issued_at", "updated_at"])
    upload = OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("visuel.png", b"fake-png", content_type="image/png"),
        original_filename="visuel.png",
        mime_type="image/png",
        size_bytes=8,
        width_mm="120.00",
        height_mm="80.00",
        support_color_hex=support_color,
    )
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        summary_message="Basic image metadata extracted.",
        image_width=1200,
        image_height=800,
    )
    return order, upload


@pytest.mark.django_db
def test_review_service_keeps_human_approval_separate_and_audited():
    actor = _staff("review_orderupload")
    order, upload = _order_with_upload()

    review = OrderUploadReviewService().review_upload(
        order=order,
        upload_public_id=upload.public_id,
        actor=actor,
        status=OrderUploadReview.Status.APPROVED,
        source="test",
    )

    assert upload.inspection.status == OrderUploadInspection.Status.OK
    assert review.status == OrderUploadReview.Status.APPROVED
    assert review.reviewed_by == actor
    assert review.reviewed_at is not None
    audit = AuditLogEntry.objects.get(action="order_upload.reviewed")
    assert audit.metadata["order_upload_public_id"] == str(upload.public_id)
    assert audit.metadata["review_status"] == "approved"
    assert "comment" not in audit.metadata


@pytest.mark.django_db
def test_review_service_rejects_control_before_of_document_is_issued():
    actor = _staff("review_orderupload")
    order, upload = _order_with_upload(of_document_issued=False)

    with pytest.raises(ValidationError, match="Imprimez d’abord l’OF"):
        OrderUploadReviewService().review_upload(
            order=order,
            upload_public_id=upload.public_id,
            actor=actor,
            status=OrderUploadReview.Status.APPROVED,
            source="test",
        )

    assert not OrderUploadReview.objects.filter(order_upload=upload).exists()
    rejection = AuditLogEntry.objects.get(action="order_upload.review_rejected")
    assert rejection.status == AuditLogEntry.Status.FAILURE
    assert rejection.metadata["reason"] == "manufacturing_order_not_issued"


@pytest.mark.django_db
def test_review_service_requires_reason_and_scopes_upload_to_order():
    actor = _staff("review_orderupload")
    order_a, _upload_a = _order_with_upload(customer_name="Client A")
    _order_b, upload_b = _order_with_upload(customer_name="Client B")
    service = OrderUploadReviewService()

    with pytest.raises(OrderUploadReviewTargetNotFound):
        service.review_upload(
            order=order_a,
            upload_public_id=upload_b.public_id,
            actor=actor,
            status=OrderUploadReview.Status.APPROVED,
            source="test",
        )
    with pytest.raises(ValidationError):
        service.review_upload(
            order=order_a,
            upload_public_id=_upload_a.public_id,
            actor=actor,
            status=OrderUploadReview.Status.CHANGES_REQUESTED,
            source="test",
        )
    assert OrderUploadReview.objects.count() == 0


@pytest.mark.django_db
def test_review_service_refuses_staff_without_review_permission():
    actor = _staff("view_orderuploadinspection")
    order, upload = _order_with_upload()

    with pytest.raises(PermissionDenied):
        OrderUploadReviewService().review_upload(
            order=order,
            upload_public_id=upload.public_id,
            actor=actor,
            status=OrderUploadReview.Status.APPROVED,
            source="test",
        )


@pytest.mark.django_db
def test_staff_inspection_panel_uses_clear_machine_and_human_labels(client):
    actor = _staff(
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "review_orderupload",
    )
    order, _upload = _order_with_upload()
    client.force_login(actor)

    response = client.get(
        reverse("portal:staff-order-panel-inspection", kwargs={"order_public_id": order.public_id})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Contrôle fichiers" in html
    assert "Analyse réussie" in html
    assert "À contrôler" in html
    assert "Approuver pour production" in html
    assert "Taille demandée" in html
    assert "120 × 80 mm" in html
    assert "Couleur du support" in html
    assert "#112233" in html
    assert ">Valide<" not in html
    assert "warning / erreur" not in html


@pytest.mark.django_db
def test_staff_inspection_panel_blocks_review_actions_before_of_is_issued(client):
    actor = _staff(
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "review_orderupload",
    )
    order, _upload = _order_with_upload(of_document_issued=False)
    client.force_login(actor)

    response = client.get(
        reverse("portal:staff-order-panel-inspection", kwargs={"order_public_id": order.public_id})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Imprimez d’abord l’OF" in html
    assert "Approuver pour production" not in html


@pytest.mark.django_db
def test_staff_inspection_panel_receives_multicolor_support_choice(client):
    actor = _staff(
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "review_orderupload",
    )
    order, _upload = _order_with_upload(support_color="#multicolor")
    client.force_login(actor)

    response = client.get(
        reverse("portal:staff-order-panel-inspection", kwargs={"order_public_id": order.public_id})
    )

    assert response.status_code == 200
    html = response.content.decode()
    assert "Couleur du support" in html
    assert "b2b-support-color-badge is-rainbow" in html
    assert "Multicolore" in html


@pytest.mark.django_db
def test_staff_can_approve_and_request_correction_via_scoped_htmx_action(client, monkeypatch):
    actor = _staff(
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "review_orderupload",
    )
    order, upload = _order_with_upload()
    client.force_login(actor)
    url = reverse(
        "portal:staff-order-upload-review",
        kwargs={"order_public_id": order.public_id, "upload_public_id": upload.public_id},
    )

    approved = client.post(url, {"status": "approved"}, HTTP_HX_REQUEST="true")
    assert approved.status_code == 200
    assert json.loads(approved["X-Prenium-Toast"])["message"] == "Fichier approuvé pour production."
    assert OrderUploadReview.objects.get(order_upload=upload).status == "approved"

    scheduled = []
    monkeypatch.setattr(
        "apps.portal.views_staff_reviews.schedule_file_correction_requested_email",
        lambda **kwargs: scheduled.append(kwargs),
    )
    correction = client.post(
        url,
        {
            "status": "changes_requested",
            "reason_code": "low_resolution",
            "comment": "Merci de fournir un fichier 300 DPI.",
        },
        HTTP_HX_REQUEST="true",
    )
    review = OrderUploadReview.objects.get(order_upload=upload)
    assert correction.status_code == 200
    assert json.loads(correction["X-Prenium-Toast"])["message"].startswith("Correction enregistrée")
    assert "=?utf-8?" not in correction["X-Prenium-Toast"]
    assert review.status == "changes_requested"
    assert review.reason_code == "low_resolution"
    assert scheduled == [{"review_public_id": review.public_id}]
    assert "Correction demandée" in correction.content.decode()


@pytest.mark.django_db
def test_staff_review_and_preview_routes_hide_upload_from_another_order(client):
    actor = _staff(
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "review_orderupload",
    )
    order_a, _upload_a = _order_with_upload(customer_name="Client A")
    _order_b, upload_b = _order_with_upload(customer_name="Client B")
    client.force_login(actor)

    review_url = reverse(
        "portal:staff-order-upload-review",
        kwargs={"order_public_id": order_a.public_id, "upload_public_id": upload_b.public_id},
    )
    preview_url = reverse(
        "portal:staff-order-upload-preview",
        kwargs={"order_public_id": order_a.public_id, "upload_public_id": upload_b.public_id},
    )

    assert client.post(review_url, {"status": "approved"}).status_code == 404
    assert client.get(preview_url).status_code == 404
    assert not OrderUploadReview.objects.exists()
