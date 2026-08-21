from __future__ import annotations

import json
import uuid

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.production.models import ProductionJob
from apps.production.services.workflow import ProductionWorkflowService
from apps.shipping.models import Shipment
from apps.shipping.services.sendcloud import SendcloudOrderResult, ShipmentService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse


class FakeSendcloudGateway:
    def build_order_payload(self, *, order, shipment_request):
        return {
            "external_reference": str(order.public_id),
            "recipient": shipment_request["recipient"],
        }

    def declare_order(self, *, payload):
        return SendcloudOrderResult(
            sendcloud_order_id="sc-operations-001",
            order_id="order-operations-001",
            order_number="OF-OPERATIONS-001",
            status_code="DECLARED",
            status_message="Déclarée",
        )


def grant(user, *codenames):
    user.user_permissions.add(
        *(Permission.objects.get(codename=codename) for codename in codenames)
    )


def staff_client(*, email: str, permissions: tuple[str, ...]):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    grant(user, "access_staff_portal", *permissions)
    client = Client()
    assert client.login(email=email, password="pass")
    return user, client


def create_order(*, actor, customer_name: str = "Atelier Client"):
    customer = Customer.objects.create(
        name=customer_name,
        billing_email="logistique@example.com",
        shipping_address_line1="Rue des Imprimeurs",
        shipping_postal_code="59000",
        shipping_city="Lille",
        shipping_country="FR",
    )
    order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.DEFERRED,
    )
    job = ProductionWorkflowService().get_or_create_for_order(order=order)
    return order, job


BASE_PERMISSIONS = (
    "view_order",
    "view_productionjob",
    "scan_productionjob",
)
TRANSITION_PERMISSIONS = (
    *BASE_PERMISSIONS,
    "transition_productionjob",
    "scan_transition_productionjob",
)


@pytest.mark.django_db
def test_operator_console_requires_staff_scope_and_scan_permissions():
    route = reverse("portal:staff-atelier-operations")
    anonymous = Client().get(route)
    assert anonymous.status_code == 302

    non_staff = get_user_model().objects.create_user(
        email="client-with-perms@example.com",
        password="pass",
    )
    grant(non_staff, *BASE_PERMISSIONS)
    client = Client()
    assert client.login(email=non_staff.email, password="pass")
    assert client.get(route).status_code == 403

    _limited_user, limited_client = staff_client(
        email="limited-operations@example.com",
        permissions=("view_order", "view_productionjob"),
    )
    assert limited_client.get(route).status_code == 403
    assert AuditLogEntry.objects.filter(
        action="production.operator_console_permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_console_lists_jobs_and_searches_by_of_without_detail_navigation():
    actor, client = staff_client(
        email="reader-operations@example.com",
        permissions=BASE_PERMISSIONS,
    )
    _first_order, first_job = create_order(actor=actor, customer_name="Premier Client")
    create_order(actor=actor, customer_name="Second Client")
    route = reverse("portal:staff-atelier-operations")

    response = client.get(route, {"q": first_job.scan_identifier})

    assert response.status_code == 200
    html = response.content.decode()
    assert "Pilotage Atelier" in html
    assert first_job.manufacturing_order_number in html
    assert "Premier Client" in html
    assert "Second Client" not in html
    assert "Consultation seule" in html
    assert "Douchette prête" in html

    partial = client.get(
        route,
        {"queue": "all"},
        HTTP_HX_REQUEST="true",
    )
    partial_html = partial.content.decode()
    assert partial.status_code == 200
    assert 'id="atelier-operations-workspace"' in partial_html
    assert "<!doctype html>" not in partial_html.lower()


@pytest.mark.django_db
def test_console_explains_payment_prerequisite_instead_of_offering_start():
    actor, client = staff_client(
        email="payment-gate-operations@example.com",
        permissions=TRANSITION_PERMISSIONS,
    )
    order, job = create_order(actor=actor)
    order.billing_mode = Order.BillingMode.IMMEDIATE
    order.pricing_status = Order.PricingStatus.PENDING
    order.save(update_fields=("billing_mode", "pricing_status", "updated_at"))

    response = client.get(reverse("portal:staff-atelier-operations"), {"q": job.scan_identifier})

    assert response.status_code == 200
    html = response.content.decode()
    assert "Démarrage en attente" in html
    assert "Résoudre le prérequis" in html
    assert "Démarrer la production" not in html


@pytest.mark.django_db
def test_console_transition_updates_one_job_and_returns_status_feedback():
    actor, client = staff_client(
        email="transition-operations@example.com",
        permissions=TRANSITION_PERMISSIONS,
    )
    order, job = create_order(actor=actor)
    route = reverse(
        "portal:staff-atelier-operation-transition",
        kwargs={"order_public_id": order.public_id},
    )

    response = client.post(
        route,
        {
            "to_status": ProductionJob.Status.IN_PROGRESS,
            "reason": "OF chargé sur la ligne 1",
            "queue": "active",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == ProductionJob.Status.IN_PROGRESS
    assert "En production" in response.content.decode()
    toast = json.loads(response["X-Prenium-Toast"])
    assert toast["variant"] == "success"
    assert job.manufacturing_order_number in toast["message"]
    assert AuditLogEntry.objects.filter(
        action="production.status_changed",
        target_public_id=job.public_id,
    ).exists()


@pytest.mark.django_db
def test_console_rejects_invalid_transition_without_changing_job():
    actor, client = staff_client(
        email="invalid-transition-operations@example.com",
        permissions=TRANSITION_PERMISSIONS,
    )
    order, job = create_order(actor=actor)
    route = reverse(
        "portal:staff-atelier-operation-transition",
        kwargs={"order_public_id": order.public_id},
    )

    response = client.post(
        route,
        {"to_status": ProductionJob.Status.COMPLETED, "queue": "active"},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    job.refresh_from_db()
    assert job.status == ProductionJob.Status.QUEUED
    assert json.loads(response["X-Prenium-Toast"])["variant"] == "error"
    assert "n’est pas" in response.content.decode() or "not allowed" in response.content.decode()


@pytest.mark.django_db
def test_console_declares_ready_order_in_sendcloud_without_opening_detail(monkeypatch):
    actor, client = staff_client(
        email="shipping-operations@example.com",
        permissions=(*TRANSITION_PERMISSIONS, "view_shipment", "create_shipment"),
    )
    order, job = create_order(actor=actor)
    job.status = ProductionJob.Status.READY_TO_SHIP
    job.save(update_fields=("status", "updated_at"))
    monkeypatch.setattr(
        "apps.portal.views_staff_operations.shipment_service",
        ShipmentService(gateway=FakeSendcloudGateway()),
    )
    route = reverse(
        "portal:staff-atelier-operation-shipment-create",
        kwargs={"order_public_id": order.public_id},
    )

    response = client.post(
        route,
        {
            "queue": "shipping",
            "recipient_name": "Atelier Client",
            "recipient_company_name": "Atelier Client",
            "recipient_email": "logistique@example.com",
            "recipient_country_code": "FR",
            "recipient_city": "Lille",
            "recipient_postal_code": "59000",
            "recipient_address_line_1": "Rue des Imprimeurs",
            "recipient_house_number": "12",
            "parcel_weight_value": "1.25",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    shipment = Shipment.objects.get(order=order)
    assert shipment.sendcloud_order_id == "sc-operations-001"
    assert shipment.status == Shipment.Status.CREATED
    html = response.content.decode()
    assert "Sendcloud déclaré" in html
    assert "Étiquette et suivi en attente" in html
    assert json.loads(response["X-Prenium-Toast"])["variant"] == "success"


@pytest.mark.django_db
def test_legacy_order_scan_panel_redirects_to_dedicated_console():
    actor, client = staff_client(
        email="legacy-scan-operations@example.com",
        permissions=BASE_PERMISSIONS,
    )
    order, job = create_order(actor=actor)
    legacy_route = reverse(
        "portal:staff-order-panel-scan",
        kwargs={"order_public_id": order.public_id},
    )

    response = client.get(legacy_route)

    assert response.status_code == 302
    assert reverse("portal:staff-atelier-operations") in response["Location"]
    assert job.scan_identifier in response["Location"]


@pytest.mark.django_db
def test_console_transition_permission_is_checked_before_order_lookup():
    _actor, client = staff_client(
        email="denied-operation-mutation@example.com",
        permissions=BASE_PERMISSIONS,
    )
    route = reverse(
        "portal:staff-atelier-operation-transition",
        kwargs={"order_public_id": uuid.uuid4()},
    )

    response = client.post(route, {"to_status": ProductionJob.Status.IN_PROGRESS})

    assert response.status_code == 403
    assert AuditLogEntry.objects.filter(
        action="production.operator_console_permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()
