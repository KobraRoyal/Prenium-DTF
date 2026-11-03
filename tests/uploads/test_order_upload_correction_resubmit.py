import json
from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.uploads.models import (
    Asset,
    AssetVersion,
    OrderUpload,
    OrderUploadDriveSync,
    OrderUploadReview,
)
from apps.uploads.services.uploads import OrderUploadService
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def _png(name="corrige.png"):
    return SimpleUploadedFile(name, PNG, content_type="image/png")


def _client_order(*, email="client-correction@example.com", status=Order.Status.SUBMITTED):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name="Client correction", billing_email=email)
    membership = CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=status,
        total_amount=Decimal("42.00"),
        pricing_status=Order.PricingStatus.PRICED,
    )
    upload = OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("visuel.png", PNG, content_type="image/png"),
        original_filename="visuel.png",
        mime_type="image/png",
        size_bytes=len(PNG),
        quantity=3,
        width_mm=Decimal("120.00"),
        height_mm=Decimal("80.00"),
        support_color_hex="#112233",
        meterage_override_linear_m=Decimal("1.5000"),
        production_file_sha256="a" * 64,
    )
    OrderUploadReview.objects.create(
        order_upload=upload,
        status=OrderUploadReview.Status.CHANGES_REQUESTED,
        reason_code=OrderUploadReview.Reason.LOW_RESOLUTION,
        comment="Passez en 300 DPI.",
        reviewed_by=user,
    )
    return user, membership, customer, order, upload


def _service():
    service = OrderUploadService()
    service.inspection_service.inspect_upload = lambda **kwargs: None
    return service


@pytest.mark.django_db
def test_replace_after_correction_keeps_commercial_data_and_reopens_review():
    user, membership, customer, order, upload = _client_order()
    service = _service()

    replaced = service.replace_after_correction(
        customer=customer,
        actor=user,
        uploaded_file=_png(),
        customer_membership=membership,
        order_public_id=order.public_id,
        upload_public_id=upload.public_id,
        source="test",
    )

    upload.refresh_from_db()
    order.refresh_from_db()
    review = upload.atelier_review
    assert replaced.original_filename == "corrige.png"
    assert upload.quantity == 3
    assert upload.width_mm == Decimal("120.00")
    assert upload.height_mm == Decimal("80.00")
    assert upload.support_color_hex == "#112233"
    assert upload.meterage_override_linear_m == Decimal("1.5000")
    assert upload.production_file_sha256 == ""
    assert upload.asset_version_id is None
    assert order.total_amount == Decimal("42.00")
    assert order.pricing_status == Order.PricingStatus.PRICED
    assert order.status == Order.Status.SUBMITTED
    assert review.status == OrderUploadReview.Status.PENDING
    assert review.reason_code == ""
    assert review.comment == ""
    sync = OrderUploadDriveSync.objects.get(order_upload=upload)
    assert sync.status == OrderUploadDriveSync.Status.PENDING
    assert sync.drive_file_id == ""
    audit = AuditLogEntry.objects.get(action="order_upload.correction_resubmitted")
    assert audit.metadata["previous_reason_code"] == "low_resolution"
    assert "Passez en 300 DPI." not in str(audit.metadata)


@pytest.mark.django_db
def test_replace_after_correction_detaches_shared_asset_without_deleting_it():
    user, membership, customer, order, upload = _client_order(email="asset-correction@example.com")
    asset = Asset.objects.create(customer=customer, name="Logo")
    version = AssetVersion(
        customer=customer,
        asset=asset,
        version_number=1,
        original_filename="visuel.png",
        mime_type="image/png",
        size_bytes=len(PNG),
        sha256="b" * 64,
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    version.file.save("bibliotheque.png", _png("bibliotheque.png"), save=True)
    library_name = version.file.name
    upload.asset_version = version
    upload.file.name = library_name
    upload.save(update_fields=["asset_version", "file", "updated_at"])

    _service().replace_after_correction(
        customer=customer,
        actor=user,
        uploaded_file=_png("nouveau.png"),
        customer_membership=membership,
        order_public_id=order.public_id,
        upload_public_id=upload.public_id,
        source="test",
    )

    upload.refresh_from_db()
    version.refresh_from_db()
    assert upload.asset_version_id is None
    assert upload.file.name != library_name
    assert version.file.name == library_name
    assert version.file.storage.exists(library_name)


@pytest.mark.django_db
def test_replace_after_correction_refuses_approved_external_and_other_customer():
    user, membership, customer, order, upload = _client_order(email="guard-correction@example.com")
    service = _service()
    review = upload.atelier_review
    review.status = OrderUploadReview.Status.APPROVED
    review.reason_code = ""
    review.comment = ""
    review.save(update_fields=["status", "reason_code", "comment", "updated_at"])

    with pytest.raises(ValidationError, match="pas en attente de correction"):
        service.replace_after_correction(
            customer=customer,
            actor=user,
            uploaded_file=_png(),
            customer_membership=membership,
            order_public_id=order.public_id,
            upload_public_id=upload.public_id,
            source="test",
        )
    upload.refresh_from_db()
    assert upload.original_filename == "visuel.png"

    review.status = OrderUploadReview.Status.CHANGES_REQUESTED
    review.reason_code = OrderUploadReview.Reason.OTHER
    review.comment = "Lien à reprendre."
    review.save(update_fields=["status", "reason_code", "comment", "updated_at"])
    upload.external_url = "https://files.example.com/visuel.zip"
    upload.file.name = ""
    upload.size_bytes = 0
    upload.asset_version = None
    upload.save(update_fields=["external_url", "file", "size_bytes", "asset_version", "updated_at"])
    with pytest.raises(ValidationError, match="lien externe"):
        service.replace_after_correction(
            customer=customer,
            actor=user,
            uploaded_file=_png(),
            customer_membership=membership,
            order_public_id=order.public_id,
            upload_public_id=upload.public_id,
            source="test",
        )

    other = Customer.objects.create(name="Autre")
    with pytest.raises(ValidationError, match="Commande introuvable"):
        service.replace_after_correction(
            customer=other,
            actor=user,
            uploaded_file=_png(),
            order_public_id=order.public_id,
            upload_public_id=upload.public_id,
            source="test",
        )


@pytest.mark.django_db
def test_submitted_order_stays_locked_for_a_new_upload():
    user, membership, customer, order, _upload = _client_order(email="lock-correction@example.com")
    with pytest.raises(ValidationError, match="verrouillée"):
        OrderUploadService().create_upload(
            customer=customer,
            actor=user,
            uploaded_file=_png("ajout.png"),
            customer_membership=membership,
            order_public_id=order.public_id,
            source="test",
        )


@pytest.mark.django_db
def test_client_panel_resubmits_only_the_file_under_correction():
    user, _membership, customer, order, upload = _client_order(email="panel-correction@example.com")
    approved = OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("ok.png", PNG, content_type="image/png"),
        original_filename="ok.png",
        mime_type="image/png",
        size_bytes=len(PNG),
        quantity=1,
        sort_order=2,
    )
    OrderUploadReview.objects.create(
        order_upload=approved,
        status=OrderUploadReview.Status.APPROVED,
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    panel_url = reverse(
        "portal:client-order-panel-uploads",
        kwargs={"customer_public_id": customer.public_id, "order_public_id": order.public_id},
    )
    panel = client.get(panel_url)
    html = panel.content.decode()
    assert panel.status_code == 200
    assert html.count("Envoyer le fichier corrigé") == 2
    assert "Passez en 300 DPI." in html
    assert "Résolution insuffisante" in html

    replace_url = reverse(
        "portal:client-order-upload-replace",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
            "upload_public_id": upload.public_id,
        },
    )
    response = client.post(replace_url, {"file": _png("corrige.png")})
    assert response.status_code == 200
    toast = json.loads(response.headers["X-Prenium-Toast"])
    assert toast["message"] == "Fichier corrigé envoyé. L’atelier va le contrôler à nouveau."
    assert toast["variant"] == "success"
    upload.refresh_from_db()
    approved.refresh_from_db()
    assert upload.original_filename == "corrige.png"
    assert upload.atelier_review.status == OrderUploadReview.Status.PENDING
    assert approved.original_filename == "ok.png"
    assert approved.atelier_review.status == OrderUploadReview.Status.APPROVED
    assert "Envoyer le fichier corrigé" not in response.content.decode()

    outsider = get_user_model().objects.create_user(email="outsider@example.com", password="pass")
    CustomerMembership.objects.create(
        customer=Customer.objects.create(name="Autre client"),
        user=outsider,
        role=CustomerMembership.Role.OWNER,
    )
    other_client = Client()
    assert other_client.login(email=outsider.email, password="pass")
    denied = other_client.post(replace_url, {"file": _png("intrus.png")})
    assert denied.status_code == 403
    upload.refresh_from_db()
    assert upload.original_filename == "corrige.png"
