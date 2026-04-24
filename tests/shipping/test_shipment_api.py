import pytest
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping import views as shipping_views
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
            raise SendcloudAPIError("Carrier unavailable.")
        return SendcloudShipmentResult(
            shipment_id="sc-shipment-123",
            parcel_id="383707309",
            status_code="READY_TO_SEND",
            status_message="Ready to send",
            tracking_number="3SYZXG8498635",
            tracking_url="https://tracking.example.test/parcel/3SYZXG8498635",
            label_content=b"%PDF-1.4 fake label",
            label_mime_type="application/pdf",
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


def staff_shipment_detail_route(order_public_id):
    return reverse(
        "shipping:staff-shipment-detail",
        kwargs={"order_public_id": order_public_id},
    )


def staff_shipment_create_route(order_public_id):
    return reverse(
        "shipping:staff-shipment-create",
        kwargs={"order_public_id": order_public_id},
    )


@pytest.mark.django_db
def test_staff_with_permissions_can_create_shipment(monkeypatch):
    staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)
    monkeypatch.setattr(
        shipping_views,
        "shipment_service",
        ShipmentService(gateway=FakeSendcloudGateway()),
    )

    response = client.post(
        staff_shipment_create_route(order.public_id),
        build_payload(),
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["order_public_id"] == str(order.public_id)
    assert payload["status"] == Shipment.Status.CREATED
    assert payload["tracking_number"] == "3SYZXG8498635"
    assert payload["tracking_url"] == "https://tracking.example.test/parcel/3SYZXG8498635"
    assert payload["label"]["has_file"] is True


@pytest.mark.django_db
def test_staff_without_dedicated_create_permission_is_refused(monkeypatch):
    staff_user, client = create_staff_client(permission_codenames=["view_shipment"])
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)
    monkeypatch.setattr(
        shipping_views,
        "shipment_service",
        ShipmentService(gateway=FakeSendcloudGateway()),
    )

    response = client.post(
        staff_shipment_create_route(order.public_id),
        build_payload(),
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_client_is_refused_on_staff_shipping_routes(monkeypatch):
    staff_user = get_user_model().objects.create_user(
        email="ops@example.com",
        password="pass",
        is_staff=True,
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)
    client = APIClient()
    assert client.login(email=actor.email, password="pass") is True
    monkeypatch.setattr(
        shipping_views,
        "shipment_service",
        ShipmentService(gateway=FakeSendcloudGateway()),
    )

    create_response = client.post(
        staff_shipment_create_route(order.public_id),
        build_payload(),
        format="json",
    )
    detail_response = client.get(staff_shipment_detail_route(order.public_id))

    assert_private_response_denied(create_response)
    assert_private_response_denied(detail_response)


@pytest.mark.django_db
def test_sendcloud_error_returns_consistent_status_and_persists_failed_shipment(monkeypatch):
    staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)
    monkeypatch.setattr(
        shipping_views,
        "shipment_service",
        ShipmentService(gateway=FakeSendcloudGateway(should_fail=True)),
    )

    response = client.post(
        staff_shipment_create_route(order.public_id),
        build_payload(),
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == ["Carrier unavailable."]
    shipment = Shipment.objects.get(order=order)
    assert shipment.status == Shipment.Status.FAILED
    assert shipment.last_error_message == "Carrier unavailable."


@pytest.mark.django_db
def test_staff_with_view_permission_can_consult_existing_shipment(monkeypatch):
    staff_user, client = create_staff_client(
        permission_codenames=["view_shipment", "create_shipment"]
    )
    actor, customer, _membership = create_customer_scope("client@example.com", "Acme")
    order = create_order(customer, actor)
    mark_order_ready_to_ship(order, actor=staff_user)
    monkeypatch.setattr(
        shipping_views,
        "shipment_service",
        ShipmentService(gateway=FakeSendcloudGateway()),
    )

    create_response = client.post(
        staff_shipment_create_route(order.public_id),
        build_payload(),
        format="json",
    )
    assert create_response.status_code == status.HTTP_201_CREATED

    _view_staff_user, view_client = create_staff_client(permission_codenames=["view_shipment"])
    response = view_client.get(staff_shipment_detail_route(order.public_id))

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["sendcloud_status"]["code"] == "READY_TO_SEND"
    assert payload["label"]["has_file"] is True
