import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment
from apps.shipping.services.sendcloud import SendcloudAPIError, ShipmentService
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
        subtotal_amount="12.50",
        total_amount="12.50",
    )


def mark_order_ready_to_ship(order, *, actor):
    workflow_service = ProductionWorkflowService()
    workflow_service.get_or_create_for_order(order=order)
    workflow_service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.IN_PROGRESS,
        actor=actor,
        source="test",
    )
    workflow_service.transition_job(
        order_public_id=order.public_id,
        to_status=ProductionJob.Status.READY_TO_SHIP,
        actor=actor,
        source="test",
    )


def build_payload():
    return {
        "shipping_option_code": "postnl:standard",
        "contract_id": 517,
        "recipient": {
            "name": "Client Demo",
            "company_name": "Acme",
            "address_line_1": "Rue de Paris",
            "address_line_2": "",
            "house_number": "12",
            "postal_code": "75001",
            "city": "Paris",
            "country_code": "FR",
            "email": "client@example.com",
            "phone_number": "+33102030405",
        },
        "parcel": {
            "weight": {
                "value": "1.250",
                "unit": "kg",
            },
            "dimensions": {
                "length": "20.00",
                "width": "15.00",
                "height": "5.00",
                "unit": "cm",
            },
        },
    }


class FakeSendcloudGateway:
    def __init__(self, *, fail_create: bool = False):
        self.fail_create = fail_create
        self.last_payload = None

    def build_request_payload(self, *, order, shipment_request):
        self.last_payload = {
            "order_public_id": str(order.public_id),
            "shipment_request": shipment_request,
        }
        return self.last_payload

    def create_shipment(self, *, payload):
        self.last_payload = payload
        if self.fail_create:
            raise SendcloudAPIError("Carrier unavailable.")
        from apps.shipping.services.sendcloud import SendcloudShipmentResult

        return SendcloudShipmentResult(
            shipment_id="shipment-123",
            parcel_id="383707309",
            status_code="READY_TO_SEND",
            status_message="Ready to send",
            tracking_number="3SYZXG8498635",
            tracking_url="https://tracking.example.test/parcel/3SYZXG8498635",
            label_content=b"%PDF-1.4 fake label",
            label_mime_type="application/pdf",
        )


@pytest.mark.django_db
def test_create_shipment_stores_label_tracking_and_audit():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)
    gateway = FakeSendcloudGateway()

    _order, shipment = ShipmentService(gateway=gateway).create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        payload=build_payload(),
        source="test",
    )

    assert shipment.status == Shipment.Status.CREATED
    assert shipment.sendcloud_shipment_id == "shipment-123"
    assert shipment.sendcloud_parcel_id == "383707309"
    assert shipment.tracking_number == "3SYZXG8498635"
    assert shipment.tracking_url == "https://tracking.example.test/parcel/3SYZXG8498635"
    assert shipment.label_file.name.endswith(".pdf")
    assert shipment.label_mime_type == "application/pdf"
    assert shipment.last_error_message == ""
    assert gateway.last_payload["order_public_id"] == str(order.public_id)
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_created",
        target_public_id=shipment.public_id,
    ).exists()


@pytest.mark.django_db
def test_sendcloud_api_error_marks_failed_and_audits_failure():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)

    with pytest.raises(ValidationError, match="Carrier unavailable."):
        ShipmentService(gateway=FakeSendcloudGateway(fail_create=True)).create_shipment(
            order_public_id=order.public_id,
            actor=staff_user,
            payload=build_payload(),
            source="test",
        )

    shipment = Shipment.objects.get(order=order)
    assert shipment.status == Shipment.Status.FAILED
    assert shipment.last_error_message == "Carrier unavailable."
    assert shipment.sendcloud_parcel_id == ""
    assert AuditLogEntry.objects.filter(
        action="shipping.shipment_creation_failed",
        target_public_id=shipment.public_id,
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_create_shipment_requires_ready_to_ship_status():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    ProductionWorkflowService().get_or_create_for_order(order=order)

    with pytest.raises(
        ValidationError,
        match="Shipment can only be created when production is ready to ship.",
    ):
        ShipmentService(gateway=FakeSendcloudGateway()).create_shipment(
            order_public_id=order.public_id,
            actor=staff_user,
            payload=build_payload(),
            source="test",
        )
