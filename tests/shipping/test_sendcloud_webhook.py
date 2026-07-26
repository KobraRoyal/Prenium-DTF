import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment
from apps.shipping.services.sendcloud import (
    SendcloudOrderResult,
    ShipmentService,
)
from apps.core.public_refs import short_public_ref
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


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
        billing_mode=Order.BillingMode.DEFERRED,
        currency="EUR",
        subtotal_amount="25.00",
        total_amount="25.00",
    )


def mark_order_ready_to_ship(order):
    workflow_service = ProductionWorkflowService()
    staff_user = get_user_model().objects.create_user(
        email=f"workflow-{order.public_id}@example.com",
        password="pass",
        is_staff=True,
    )
    workflow_service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=staff_user,
        source="test",
    )
    workflow_service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.READY_TO_SHIP,
        actor=staff_user,
        source="test",
    )


def build_shipment_payload():
    return {
        "shipping_option_code": "sendcloud:letter",
        "recipient": {
            "name": "Jean Test",
            "address_line_1": "1 rue des Fleurs",
            "house_number": "12",
            "postal_code": "75001",
            "city": "Paris",
            "country_code": "FR",
            "email": "jean@example.com",
        },
        "parcel": {"weight": {"value": "1.250", "unit": "kg"}},
    }


class FakeSendcloudGateway:
    def build_order_payload(self, *, order, shipment_request):
        return [{"order_public_id": str(order.public_id)}]

    def declare_order(self, *, payload):
        return SendcloudOrderResult(
            sendcloud_order_id="sc-order-wh",
            order_id="order-ext-wh",
            order_number="order-ext-wh",
            status_code="DECLARED",
            status_message="Declared in Sendcloud — awaiting label",
        )

    def fetch_parcel(self, *, parcel_id: str):
        return {
            "id": parcel_id,
            "tracking_number": "TRK-123456",
            "tracking_url": "https://tracking.example.test/TRK-123456",
            "status": {"code": "READY_TO_SEND", "message": "Ready"},
        }


def _sendcloud_signature(*, payload: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def _create_created_shipment():
    actor, customer, _membership = create_customer_scope("wh-client@example.com", "Acme WH")
    staff_user = get_user_model().objects.create_user(
        email="wh-staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    _order, shipment = ShipmentService(gateway=FakeSendcloudGateway()).create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )
    shipment.sendcloud_parcel_id = "383707309"
    shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])
    return order, shipment


@pytest.mark.django_db
@override_settings(SENDCLOUD_WEBHOOK_SECRET="whsec_sendcloud_test")
def test_sendcloud_webhook_updates_tracking_and_notifies_once():
    order, shipment = _create_created_shipment()
    payload = json.dumps(
        {
            "id": shipment.sendcloud_parcel_id,
            "tracking_number": "TRK-WH-001",
            "tracking_url": "https://tracking.example.test/TRK-WH-001",
            "status": {"code": "IN_TRANSIT", "message": "En transit"},
        }
    ).encode("utf-8")
    signature = _sendcloud_signature(payload=payload, secret="whsec_sendcloud_test")
    client = APIClient()

    with patch(
        "apps.notifications.services.transactional.schedule_order_shipped_email"
    ) as shipped_schedule:
        response = client.post(
            reverse("shipping:backend-sendcloud-webhook"),
            data=payload,
            content_type="application/json",
            HTTP_SENDCLOUD_SIGNATURE=signature,
        )
        response_repeat = client.post(
            reverse("shipping:backend-sendcloud-webhook"),
            data=payload,
            content_type="application/json",
            HTTP_SENDCLOUD_SIGNATURE=signature,
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["matched"] is True
    assert response_repeat.status_code == status.HTTP_200_OK
    shipment.refresh_from_db()
    assert shipment.tracking_number == "TRK-WH-001"
    assert shipment.sendcloud_status_code == "IN_TRANSIT"
    assert shipment.shipped_at is not None
    shipped_schedule.assert_called_once_with(order_public_id=order.public_id)
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_tracking_synced",
        target_public_id=shipment.public_id,
    ).exists()
    from apps.production.models import ProductionJob

    job = ProductionJob.objects.get(order=order)
    assert job.status == ProductionJob.Status.COMPLETED
    assert job.completed_at is not None


@pytest.mark.django_db
@override_settings(SENDCLOUD_WEBHOOK_SECRET="whsec_sendcloud_test")
def test_sendcloud_webhook_rejects_invalid_signature():
    payload = b'{"id":"1","status":{"code":"IN_TRANSIT"}}'
    client = APIClient()
    response = client.post(
        reverse("shipping:backend-sendcloud-webhook"),
        data=payload,
        content_type="application/json",
        HTTP_SENDCLOUD_SIGNATURE="deadbeef",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert AuditLogEntry.objects.filter(
        action="security.sendcloud_webhook_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
@override_settings(SENDCLOUD_WEBHOOK_SECRET="whsec_sendcloud_test")
def test_sendcloud_webhook_unknown_parcel_is_acknowledged():
    payload = json.dumps(
        {
            "id": "unknown-parcel",
            "tracking_number": "TRK-X",
            "status": {"code": "IN_TRANSIT", "message": "En transit"},
        }
    ).encode("utf-8")
    signature = _sendcloud_signature(payload=payload, secret="whsec_sendcloud_test")
    client = APIClient()
    response = client.post(
        reverse("shipping:backend-sendcloud-webhook"),
        data=payload,
        content_type="application/json",
        HTTP_SENDCLOUD_SIGNATURE=signature,
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.data["matched"] is False
    assert AuditLogEntry.objects.filter(
        action="shipping.sendcloud_webhook_unknown_parcel",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
@override_settings(SENDCLOUD_WEBHOOK_SECRET="whsec_sendcloud_test")
def test_sendcloud_webhook_skips_stale_event():
    _order, shipment = _create_created_shipment()
    shipment.last_api_sync_at = timezone.now()
    shipment.save(update_fields=["last_api_sync_at", "updated_at"])
    stale_ts = (timezone.now() - timedelta(hours=2)).isoformat()
    payload = json.dumps(
        {
            "id": shipment.sendcloud_parcel_id,
            "tracking_number": "TRK-STALE",
            "tracking_url": "https://tracking.example.test/TRK-STALE",
            "status": {"code": "DELIVERED", "message": "Livré"},
            "timestamp": stale_ts,
        }
    ).encode("utf-8")
    signature = _sendcloud_signature(payload=payload, secret="whsec_sendcloud_test")
    client = APIClient()
    response = client.post(
        reverse("shipping:backend-sendcloud-webhook"),
        data=payload,
        content_type="application/json",
        HTTP_SENDCLOUD_SIGNATURE=signature,
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["matched"] is True
    shipment.refresh_from_db()
    assert shipment.tracking_number == ""
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_tracking_sync_skipped_stale",
        target_public_id=shipment.public_id,
    ).exists()


@pytest.mark.django_db
@override_settings(SENDCLOUD_WEBHOOK_SECRET="whsec_sendcloud_test")
def test_sendcloud_webhook_matches_by_order_number_when_parcel_unknown():
    order, shipment = _create_created_shipment()
    shipment.sendcloud_parcel_id = ""
    shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])
    payload = json.dumps(
        {
            "id": "parcel-from-label-999",
            "order_number": short_public_ref(order.public_id),
            "tracking_number": "TRK-BY-ORDER",
            "tracking_url": "https://tracking.example.test/TRK-BY-ORDER",
            "status": {"code": "IN_TRANSIT", "message": "En transit"},
        }
    ).encode("utf-8")
    signature = _sendcloud_signature(payload=payload, secret="whsec_sendcloud_test")
    client = APIClient()

    with patch(
        "apps.notifications.services.transactional.schedule_order_shipped_email"
    ) as shipped_schedule:
        response = client.post(
            reverse("shipping:backend-sendcloud-webhook"),
            data=payload,
            content_type="application/json",
            HTTP_SENDCLOUD_SIGNATURE=signature,
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["matched"] is True
    shipment.refresh_from_db()
    assert shipment.sendcloud_parcel_id == "parcel-from-label-999"
    assert shipment.tracking_number == "TRK-BY-ORDER"
    assert shipment.shipped_at is not None
    shipped_schedule.assert_called_once_with(order_public_id=order.public_id)


@pytest.mark.django_db
def test_staff_can_download_shipment_label():
    order, shipment = _create_created_shipment()
    from django.core.files.base import ContentFile

    shipment.label_filename = "legacy-label.pdf"
    shipment.label_mime_type = "application/pdf"
    shipment.label_file.save("legacy-label.pdf", ContentFile(b"%PDF-1.4 fake label"), save=True)
    staff_user = get_user_model().objects.create_user(
        email="label-staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_shipment"),
    )
    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True

    response = client.get(
        reverse("shipping:staff-shipment-label-download", kwargs={"order_public_id": order.public_id})
    )
    assert response.status_code == status.HTTP_200_OK
    assert response["Content-Type"] == "application/pdf"
    assert b"%PDF" in b"".join(response.streaming_content)
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_label_downloaded",
        target_public_id=shipment.public_id,
    ).exists()


@pytest.mark.django_db
def test_client_cannot_download_shipment_label():
    order, _shipment = _create_created_shipment()
    actor, _customer, _membership = create_customer_scope("label-client@example.com", "Other")
    client = APIClient()
    assert client.login(email=actor.email, password="pass") is True
    response = client.get(
        reverse("shipping:staff-shipment-label-download", kwargs={"order_public_id": order.public_id})
    )
    assert response.status_code in {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN}
