from unittest.mock import patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment
from apps.shipping.services.sendcloud import (
    SendcloudAPIError,
    SendcloudShipmentResult,
    ShipmentService,
)
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


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
        subtotal_amount="25.00",
        total_amount="25.00",
        customer_note="Ship me safely",
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
    _order, job, _transition = workflow_service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.READY_TO_SHIP,
        actor=staff_user,
        source="test",
    )
    return job


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
            "phone_number": "+33102030405",
        },
        "parcel": {
            "weight": {
                "value": "1.250",
                "unit": "kg",
            },
            "dimensions": {
                "length": "30",
                "width": "20",
                "height": "10",
                "unit": "cm",
            },
        },
    }


class FakeSendcloudGateway:
    def __init__(self, *, should_fail: bool = False):
        self.should_fail = should_fail
        self.last_payload = None

    def build_request_payload(self, *, order, shipment_request):
        self.last_payload = {
            "order_public_id": str(order.public_id),
            "shipment_request": shipment_request,
        }
        return self.last_payload

    def create_shipment(self, *, payload):
        self.last_payload = payload
        if self.should_fail:
            raise SendcloudAPIError("Remote carrier timeout for order. secret_key=should-not-leak")
        return SendcloudShipmentResult(
            shipment_id="sc-shipment-123",
            parcel_id="383707309",
            status_code="READY_TO_SEND",
            status_message="Ready to send",
            tracking_number="TRK-123456",
            tracking_url="https://tracking.example.test/TRK-123456",
            label_content=b"%PDF-1.4 fake label",
            label_mime_type="application/pdf",
        )

    def fetch_parcel(self, *, parcel_id: str):
        return {
            "id": parcel_id,
            "tracking_number": "TRK-UPDATED",
            "tracking_url": "https://tracking.example.test/TRK-UPDATED",
            "status": {"code": "DELIVERED", "message": "Livré"},
        }


@pytest.mark.django_db
def test_sendcloud_service_creates_shipment_and_stores_label_tracking():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    gateway = FakeSendcloudGateway()

    _order, shipment = ShipmentService(gateway=gateway).create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )

    assert shipment.status == Shipment.Status.CREATED
    assert shipment.sendcloud_shipment_id == "sc-shipment-123"
    assert shipment.sendcloud_parcel_id == "383707309"
    assert shipment.tracking_number == "TRK-123456"
    assert shipment.tracking_url == "https://tracking.example.test/TRK-123456"
    assert shipment.label_filename.endswith("sendcloud-label.pdf")
    assert shipment.label_mime_type == "application/pdf"
    assert shipment.label_retrieved_at is not None
    assert shipment.label_file.name.endswith(".pdf")
    assert shipment.request_snapshot["shipping_option_code"] == "sendcloud:letter"
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_created",
        target_public_id=shipment.public_id,
    ).exists()


@pytest.mark.django_db
def test_sync_shipment_tracking_updates_carrier_fields():
    actor, customer, _membership = create_customer_scope("sync@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-sync@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    gateway = FakeSendcloudGateway()
    service = ShipmentService(gateway=gateway)
    service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )

    with patch(
        "apps.notifications.services.transactional.schedule_order_shipped_email"
    ) as shipped_schedule:
        _order, shipment = service.sync_shipment_tracking_from_sendcloud(
            order_public_id=order.public_id,
            actor=staff_user,
            source="test",
        )
        service.sync_shipment_tracking_from_sendcloud(
            order_public_id=order.public_id,
            actor=staff_user,
            source="test-repeat",
        )

    assert shipment is not None
    assert shipment.sendcloud_status_code == "DELIVERED"
    assert shipment.sendcloud_status_message == "Livré"
    assert shipment.tracking_number == "TRK-UPDATED"
    assert shipment.shipped_at is not None
    shipped_schedule.assert_called_once_with(order_public_id=order.public_id)
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_tracking_synced",
        target_public_id=shipment.public_id,
    ).exists()


@pytest.mark.django_db
def test_sendcloud_service_refuses_duplicate_created_shipment():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    service = ShipmentService(gateway=FakeSendcloudGateway())

    service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )

    with pytest.raises(ValidationError, match="A shipment already exists for this order."):
        service.create_shipment(
            order_public_id=order.public_id,
            actor=staff_user,
            source="test",
            payload=build_shipment_payload(),
        )


@pytest.mark.django_db
def test_sendcloud_service_marks_failed_when_api_errors():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    service = ShipmentService(gateway=FakeSendcloudGateway(should_fail=True))

    with pytest.raises(ValidationError, match="Remote carrier timeout for order."):
        service.create_shipment(
            order_public_id=order.public_id,
            actor=staff_user,
            source="test",
            payload=build_shipment_payload(),
        )

    shipment = Shipment.objects.get(order=order)
    assert shipment.status == Shipment.Status.FAILED
    assert "secret_key" not in shipment.last_error_message
    assert "[redacted]" in shipment.last_error_message
    assert shipment.sendcloud_shipment_id == ""
    assert shipment.sendcloud_parcel_id == ""
    assert shipment.tracking_number == ""
    assert not shipment.label_file
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_creation_failed",
        target_public_id=shipment.public_id,
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_sendcloud_service_requires_ready_to_ship_status():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)

    with pytest.raises(
        ValidationError,
        match="Shipment can only be created when production is ready to ship.",
    ):
        ShipmentService(gateway=FakeSendcloudGateway()).create_shipment(
            order_public_id=order.public_id,
            actor=staff_user,
            source="test",
            payload=build_shipment_payload(),
        )


@pytest.mark.django_db
def test_sendcloud_service_get_staff_shipment_records_view_audit():
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    service = ShipmentService(gateway=FakeSendcloudGateway())
    service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )

    _order, shipment = service.get_staff_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test_view",
    )

    assert shipment is not None
    assert shipment.order == order
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_viewed",
        target_public_id=shipment.public_id,
    ).exists()
