import json
import re

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.uploads.models import OrderUpload
from apps.uploads.services.uploads import OrderUploadService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone


def _staff(*codenames: str):
    user = get_user_model().objects.create_user(
        email=f"qty-staff-{get_user_model().objects.count()}@example.com",
        password="pass",
        is_staff=True,
    )
    requested = ["access_staff_portal", *codenames]
    user.user_permissions.set(Permission.objects.filter(codename__in=requested))
    return user


def _atelier_staff():
    return _staff(
        "view_order",
        "view_orderupload",
        "view_orderuploadinspection",
        "review_orderupload",
    )


def _deferred_order_with_upload(*, quantity: int = 1, status=Order.Status.SUBMITTED):
    customer = Customer.objects.create(
        name=f"Client Qty {Customer.objects.count()}",
        billing_email="client@example.com",
    )
    order = Order.objects.create(
        customer=customer,
        status=status,
        billing_mode=Order.BillingMode.DEFERRED,
    )
    ProductionWorkflowService().get_or_create_for_order(order=order)
    upload = OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("visuel.png", b"fake-png", content_type="image/png"),
        original_filename="visuel.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=quantity,
        width_mm="120.00",
        height_mm="80.00",
    )
    return order, upload


@pytest.mark.django_db
def test_set_staff_upload_quantity_updates_and_audits_without_repricing():
    actor = _atelier_staff()
    order, upload = _deferred_order_with_upload(quantity=2)
    previous_total = order.total_amount

    updated = OrderUploadService().set_staff_upload_quantity(
        order=order,
        upload_public_id=upload.public_id,
        actor=actor,
        quantity=5,
        source="test",
    )

    upload.refresh_from_db()
    order.refresh_from_db()
    assert updated.quantity == 5
    assert upload.quantity == 5
    assert order.total_amount == previous_total
    audit = AuditLogEntry.objects.get(action="order_upload.quantity_updated")
    assert audit.metadata["previous_quantity"] == 2
    assert audit.metadata["quantity"] == 5
    assert audit.metadata["order_upload_public_id"] == str(upload.public_id)


@pytest.mark.django_db
def test_set_staff_upload_quantity_refuses_immediate_billing():
    actor = _atelier_staff()
    customer = Customer.objects.create(name="Comptant", billing_email="c@example.com")
    order = Order.objects.create(
        customer=customer,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    ProductionWorkflowService().get_or_create_for_order(order=order)
    upload = OrderUpload.objects.create(
        order=order,
        file=SimpleUploadedFile("visuel.png", b"fake-png", content_type="image/png"),
        original_filename="visuel.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )

    with pytest.raises(ValidationError, match="encours"):
        OrderUploadService().set_staff_upload_quantity(
            order=order,
            upload_public_id=upload.public_id,
            actor=actor,
            quantity=3,
        )


@pytest.mark.django_db
def test_set_staff_upload_quantity_refuses_when_production_started():
    actor = _atelier_staff()
    order, upload = _deferred_order_with_upload()
    job = order.production_job
    job.status = ProductionJob.Status.IN_PROGRESS
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])

    with pytest.raises(ValidationError, match="production"):
        OrderUploadService().set_staff_upload_quantity(
            order=order,
            upload_public_id=upload.public_id,
            actor=actor,
            quantity=4,
        )


@pytest.mark.django_db
def test_staff_inspection_shows_quantity_editor_for_deferred_only(client):
    actor = _atelier_staff()
    deferred, upload = _deferred_order_with_upload(quantity=3)
    client.force_login(actor)

    response = client.get(
        reverse(
            "portal:staff-order-panel-inspection",
            kwargs={"order_public_id": deferred.public_id},
        )
    )
    assert response.status_code == 200
    html = response.content.decode()
    assert "Exemplaires" in html
    assert 'name="quantity"' in html
    assert 'value="3"' in html
    assert f"/uploads/{upload.public_id}/quantity/" in html

    immediate_customer = Customer.objects.create(name="CB", billing_email="cb@example.com")
    immediate = Order.objects.create(
        customer=immediate_customer,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
    )
    ProductionWorkflowService().get_or_create_for_order(order=immediate)
    OrderUpload.objects.create(
        order=immediate,
        file=SimpleUploadedFile("visuel.png", b"fake-png", content_type="image/png"),
        original_filename="visuel.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=7,
    )
    immediate_html = client.get(
        reverse(
            "portal:staff-order-panel-inspection",
            kwargs={"order_public_id": immediate.public_id},
        )
    ).content.decode()
    assert "Exemplaires" in immediate_html
    assert re.search(r"Exemplaires</dt>\s*<dd>\s*7\s*</dd>", immediate_html)
    assert "/quantity/" not in immediate_html
    assert 'name="quantity"' not in immediate_html


@pytest.mark.django_db
def test_staff_can_update_quantity_while_job_still_queued(client):
    """« En traitement » = ProductionJob queued : édition encore autorisée."""
    actor = _atelier_staff()
    order, upload = _deferred_order_with_upload(quantity=2)
    assert order.production_job.status == ProductionJob.Status.QUEUED
    assert order.production_job.started_at is None
    client.force_login(actor)

    response = client.get(
        reverse(
            "portal:staff-order-panel-inspection",
            kwargs={"order_public_id": order.public_id},
        )
    )
    assert response.status_code == 200
    assert 'name="quantity"' in response.content.decode()

    post = client.post(
        reverse(
            "portal:staff-order-upload-quantity",
            kwargs={
                "order_public_id": order.public_id,
                "upload_public_id": upload.public_id,
            },
        ),
        {"quantity": "6"},
        HTTP_HX_REQUEST="true",
    )
    assert post.status_code == 200
    assert json.loads(post["X-Prenium-Toast"])["variant"] == "success"
    upload.refresh_from_db()
    assert upload.quantity == 6


@pytest.mark.django_db
def test_staff_without_review_permission_cannot_edit_quantity(client):
    actor = _staff("view_order", "view_orderupload", "view_orderuploadinspection")
    order, upload = _deferred_order_with_upload()
    client.force_login(actor)

    panel = client.get(
        reverse(
            "portal:staff-order-panel-inspection",
            kwargs={"order_public_id": order.public_id},
        )
    )
    assert panel.status_code == 200
    assert 'name="quantity"' not in panel.content.decode()

    denied = client.post(
        reverse(
            "portal:staff-order-upload-quantity",
            kwargs={
                "order_public_id": order.public_id,
                "upload_public_id": upload.public_id,
            },
        ),
        {"quantity": "4"},
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_staff_can_update_quantity_via_htmx(client):
    actor = _atelier_staff()
    order, upload = _deferred_order_with_upload(quantity=1)
    client.force_login(actor)
    url = reverse(
        "portal:staff-order-upload-quantity",
        kwargs={
            "order_public_id": order.public_id,
            "upload_public_id": upload.public_id,
        },
    )

    response = client.post(url, {"quantity": "8"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert json.loads(response["X-Prenium-Toast"])["message"] == "Quantité mise à jour."
    upload.refresh_from_db()
    assert upload.quantity == 8


@pytest.mark.django_db
def test_staff_quantity_endpoint_scopes_upload_to_order(client):
    actor = _atelier_staff()
    order_a, _upload_a = _deferred_order_with_upload()
    _order_b, upload_b = _deferred_order_with_upload()
    client.force_login(actor)

    response = client.post(
        reverse(
            "portal:staff-order-upload-quantity",
            kwargs={
                "order_public_id": order_a.public_id,
                "upload_public_id": upload_b.public_id,
            },
        ),
        {"quantity": "9"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    toast = json.loads(response["X-Prenium-Toast"])
    assert toast["variant"] == "error"
    assert "introuvable" in toast["message"].lower()
    upload_b.refresh_from_db()
    assert upload_b.quantity == 1
