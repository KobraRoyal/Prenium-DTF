import pytest
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
from django.contrib.auth.models import Permission
from django.urls import reverse
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


def shipment_detail_route(order_public_id):
    return reverse("shipping:staff-shipment-detail", kwargs={"order_public_id": order_public_id})


def shipment_create_route(order_public_id):
    return reverse("shipping:staff-shipment-create", kwargs={"order_public_id": order_public_id})


def shipment_sync_route(order_public_id):
    return reverse(
        "shipping:staff-shipment-sync-tracking",
        kwargs={"order_public_id": order_public_id},
    )


def client_shipment_route(customer_public_id, order_public_id):
    return reverse(
        "shipping:client-shipment-detail",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
        },
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
            "phone_number": "+33102030405",
        },
        "parcel": {
            "weight": {
                "value": "1.250",
                "unit": "kg",
            }
        },
    }


class FakeSendcloudGateway:
    def __init__(self, *, should_fail: bool = False):
        self.should_fail = should_fail

    def build_request_payload(self, *, order, shipment_request):
        return {
            "order_public_id": str(order.public_id),
            "shipment_request": shipment_request,
        }

    def create_shipment(self, *, payload):
        if self.should_fail:
            raise SendcloudAPIError("Carrier timeout")
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


@pytest.fixture
def monkeypatched_shipment_service(monkeypatch):
    def _apply(*, should_fail: bool = False):
        service = ShipmentService(gateway=FakeSendcloudGateway(should_fail=should_fail))
        monkeypatch.setattr("apps.shipping.views.shipment_service", service)
        return service

    return _apply


@pytest.mark.django_db
def test_staff_with_permission_can_create_shipment(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service()
    _staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )

    response = client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["order_public_id"] == str(order.public_id)
    assert payload["status"] == Shipment.Status.CREATED
    assert payload["tracking_number"] == "TRK-123456"
    assert payload["label"]["has_file"] is True
    assert "panel.sendcloud.sc" not in str(payload)


@pytest.mark.django_db
def test_staff_with_permission_can_view_shipment_detail(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    service = monkeypatched_shipment_service()
    staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    service.create_shipment(
        order_public_id=order.public_id,
        actor=staff_user,
        source="test",
        payload=build_shipment_payload(),
    )

    response = client.get(shipment_detail_route(order.public_id))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["public_id"] == str(Shipment.objects.get(order=order).public_id)
    assert payload["label"]["filename"].endswith(".pdf")
    assert "secret" not in str(payload).lower()
    assert "file_path" not in str(payload)


@pytest.mark.django_db
def test_staff_without_create_permission_is_refused(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service()
    _staff_user, client = create_staff_client(permission_codenames=["view_shipment"])

    response = client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_staff_without_view_permission_is_refused(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service()
    _staff_user, client = create_staff_client(permission_codenames=["create_shipment"])

    create_response = client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )
    detail_response = client.get(shipment_detail_route(order.public_id))

    assert create_response.status_code == status.HTTP_403_FORBIDDEN
    assert detail_response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_client_is_refused_on_shipping_routes(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service()
    client = APIClient()
    assert client.login(email=actor.email, password="pass") is True

    detail_response = client.get(shipment_detail_route(order.public_id))
    create_response = client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )

    assert_private_response_denied(detail_response)
    assert_private_response_denied(create_response)


@pytest.mark.django_db
def test_unknown_order_returns_404_on_staff_shipping_routes(monkeypatched_shipment_service):
    monkeypatched_shipment_service()
    _staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    missing_order = "0a0f6d27-63a9-49ac-a52f-6e9cd4f91731"

    detail_response = client.get(shipment_detail_route(missing_order))
    create_response = client.post(
        shipment_create_route(missing_order),
        build_shipment_payload(),
        format="json",
    )

    assert detail_response.status_code == status.HTTP_404_NOT_FOUND
    assert create_response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_create_shipment_route_returns_consistent_error_when_sendcloud_fails(
    monkeypatched_shipment_service,
):
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service(should_fail=True)
    _staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )

    response = client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Carrier timeout" in str(response.json())
    shipment = Shipment.objects.get(order=order)
    assert shipment.status == Shipment.Status.FAILED


@pytest.mark.django_db
def test_staff_can_sync_tracking(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("sync-api@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service()
    _staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )

    create_response = client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    sync_response = client.post(
        shipment_sync_route(order.public_id),
        {},
        format="json",
    )
    assert sync_response.status_code == status.HTTP_200_OK
    payload = sync_response.json()
    assert payload["tracking_number"] == "TRK-UPDATED"
    assert payload["sendcloud_status"]["code"] == "DELIVERED"


@pytest.mark.django_db
def test_client_can_read_scoped_shipment_without_internal_ids(monkeypatched_shipment_service):
    actor, customer, _membership = create_customer_scope("client-ship@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order)
    monkeypatched_shipment_service()
    _staff_user, staff_client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    staff_client.post(
        shipment_create_route(order.public_id),
        build_shipment_payload(),
        format="json",
    )

    client = APIClient()
    assert client.login(email=actor.email, password="pass") is True
    response = client.get(client_shipment_route(customer.public_id, order.public_id))
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["tracking_number"] == "TRK-123456"
    assert body["carrier_status"]["message"] == "Ready to send"
    assert "sendcloud_parcel" not in body
    assert "request_snapshot" not in body


@pytest.mark.django_db
def test_client_cannot_read_shipment_for_other_customer(monkeypatched_shipment_service):
    actor_a, customer_a, _ = create_customer_scope("a@example.com", "A")
    actor_b, customer_b, _ = create_customer_scope("b@example.com", "B")
    order_b = create_order(customer_b, actor_b)
    mark_order_ready_to_ship(order_b)
    monkeypatched_shipment_service()
    _staff_user, staff_client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    staff_client.post(
        shipment_create_route(order_b.public_id),
        build_shipment_payload(),
        format="json",
    )

    client = APIClient()
    assert client.login(email=actor_a.email, password="pass") is True
    response = client.get(client_shipment_route(customer_a.public_id, order_b.public_id))
    assert response.status_code == status.HTTP_404_NOT_FOUND
