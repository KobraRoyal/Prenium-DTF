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
    SendcloudOrderResult,
    ShipmentService,
)
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings


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
    def __init__(
        self,
        *,
        should_fail: bool = False,
        fetch_parcel_error: SendcloudAPIError | None = None,
        parcels_by_order_number: dict | None = None,
    ):
        self.should_fail = should_fail
        self.fetch_parcel_error = fetch_parcel_error
        self.parcels_by_order_number = parcels_by_order_number or {}
        self.last_payload = None

    def build_order_payload(self, *, order, shipment_request):
        self.last_payload = {
            "order_public_id": str(order.public_id),
            "shipment_request": shipment_request,
        }
        return [self.last_payload]

    def declare_order(self, *, payload):
        self.last_payload = payload
        if self.should_fail:
            raise SendcloudAPIError("Remote carrier timeout for order. secret_key=should-not-leak")
        return SendcloudOrderResult(
            sendcloud_order_id="sc-order-123",
            order_id="order-ext-1",
            order_number="order-ext-1",
            status_code="DECLARED",
            status_message="Declared in Sendcloud — awaiting label",
        )

    def find_parcels_for_order_number(self, *, order_number: str):
        return list(self.parcels_by_order_number.get(str(order_number), []))

    def fetch_parcel(self, *, parcel_id: str):
        if self.fetch_parcel_error is not None:
            raise self.fetch_parcel_error
        return {
            "id": parcel_id,
            "tracking_number": "TRK-UPDATED",
            "tracking_url": "https://tracking.example.test/TRK-UPDATED",
            "status": {"code": "DELIVERED", "message": "Livré"},
        }


@pytest.mark.django_db
def test_sendcloud_service_declares_order_without_label():
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
    assert shipment.sendcloud_order_id == "sc-order-123"
    assert shipment.sendcloud_parcel_id == ""
    assert shipment.tracking_number == ""
    assert shipment.tracking_url == ""
    assert shipment.sendcloud_status_code == "DECLARED"
    assert not shipment.label_file
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
    _order, shipment = service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )
    shipment.sendcloud_parcel_id = "383707309"
    shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])

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
    from apps.production.models import ProductionJob

    assert ProductionJob.objects.get(order=order).status == ProductionJob.Status.COMPLETED


@pytest.mark.django_db
def test_sync_tracking_falls_back_when_stored_parcel_id_is_404():
    from apps.core.public_refs import short_public_ref

    actor, customer, _membership = create_customer_scope("sync-404@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-sync-404@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    short_ref = short_public_ref(order.public_id)
    gateway = FakeSendcloudGateway(
        fetch_parcel_error=SendcloudAPIError(
            "Sendcloud request failed with HTTP 404.",
            status_code=404,
        ),
        parcels_by_order_number={
            short_ref: [
                {
                    "id": "parcel-real-999",
                    "tracking_number": "TRK-FALLBACK",
                    "tracking_url": "https://tracking.example.test/TRK-FALLBACK",
                    "status": {"code": "EN_ROUTE", "message": "En transit"},
                }
            ]
        },
    )
    service = ShipmentService(gateway=gateway)
    _order, shipment = service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )
    shipment.sendcloud_parcel_id = "stale-or-order-id"
    shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])

    _order, shipment = service.sync_shipment_tracking_from_sendcloud(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
    )

    assert shipment is not None
    assert shipment.sendcloud_parcel_id == "parcel-real-999"
    assert shipment.tracking_number == "TRK-FALLBACK"
    assert shipment.sendcloud_status_code == "EN_ROUTE"


@pytest.mark.django_db
def test_sync_tracking_still_raises_non_404_fetch_errors():
    actor, customer, _membership = create_customer_scope("sync-500@example.com", "Acme")
    staff_user = get_user_model().objects.create_user(
        email="staff-sync-500@example.com",
        password="pass",
        is_staff=True,
    )
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    gateway = FakeSendcloudGateway(
        fetch_parcel_error=SendcloudAPIError(
            "Sendcloud request failed with HTTP 500.",
            status_code=500,
        ),
    )
    service = ShipmentService(gateway=gateway)
    _order, shipment = service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )
    shipment.sendcloud_parcel_id = "any-id"
    shipment.save(update_fields=["sendcloud_parcel_id", "updated_at"])

    with pytest.raises(ValidationError, match="HTTP 500"):
        service.sync_shipment_tracking_from_sendcloud(
            order_public_id=order.public_id,
            actor=staff_user,
            source="test",
        )


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
    assert shipment.sendcloud_order_id == ""
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


@pytest.mark.django_db
@override_settings(
    SENDCLOUD_PUBLIC_KEY="pk_test",
    SENDCLOUD_SECRET_KEY="sk_test",
    SENDCLOUD_INTEGRATION_ID=605520,
)
def test_build_order_payload_sends_recipient_products_and_order_number_only():
    from apps.catalog.models import CatalogService
    from apps.core.public_refs import short_public_ref
    from apps.orders.models import OrderLine
    from apps.shipping.services.sendcloud import SendcloudGateway

    actor, customer, _membership = create_customer_scope("payload@example.com", "Acme")
    order = create_order(customer, actor)
    service = CatalogService.objects.create(
        code="dtf-print",
        name="Impression DTF",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
        currency="EUR",
        is_active=True,
    )
    OrderLine.objects.create(
        order=order,
        service=service,
        position=1,
        service_code=service.code,
        service_name=service.name,
        service_type=service.service_type,
        unit=service.unit,
        quantity="2.00",
        unit_price="10.00",
        line_total="20.00",
    )

    gateway = SendcloudGateway()
    payload = gateway.build_order_payload(
        order=order,
        shipment_request=build_shipment_payload(),
    )[0]

    assert payload["order_id"] == str(order.public_id)
    assert payload["order_number"] == short_public_ref(order.public_id)
    assert payload["shipping_address"]["name"] == "Jean Test"
    assert payload["shipping_address"]["postal_code"] == "75001"
    assert "from_address" not in payload
    assert payload["order_details"]["order_items"][0]["name"] == "Impression DTF"
    assert payload["order_details"]["order_items"][0]["quantity"] == 2
    assert isinstance(payload["order_details"]["order_items"][0]["quantity"], int)
    assert "delivery_indicator" not in payload.get("shipping_details", {})


@pytest.mark.django_db
@override_settings(
    SENDCLOUD_PUBLIC_KEY="pk_test",
    SENDCLOUD_SECRET_KEY="sk_test",
    SENDCLOUD_INTEGRATION_ID=605520,
)
def test_build_order_payload_ceils_fractional_quantities_to_int():
    from apps.catalog.models import CatalogService
    from apps.orders.models import OrderLine
    from apps.shipping.services.sendcloud import SendcloudGateway

    actor, customer, _membership = create_customer_scope("qty@example.com", "Acme")
    order = create_order(customer, actor)
    service = CatalogService.objects.create(
        code="dtf-frac",
        name="DTF fraction",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="10.00",
    )
    OrderLine.objects.create(
        order=order,
        service=service,
        position=1,
        service_code=service.code,
        service_name=service.name,
        service_type=service.service_type,
        unit=service.unit,
        quantity="0.99",
        unit_price="10.00",
        line_total="9.90",
    )
    payload = SendcloudGateway().build_order_payload(
        order=order,
        shipment_request=build_shipment_payload(),
    )[0]
    assert payload["order_details"]["order_items"][0]["quantity"] == 1
