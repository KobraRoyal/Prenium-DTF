import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing import views as billing_views
from apps.billing.models import Invoice, Payment
from apps.billing.services.payments import PaymentService
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


def assert_private_response_denied(response):
    assert response.status_code in {
        status.HTTP_401_UNAUTHORIZED,
        status.HTTP_403_FORBIDDEN,
    }


def create_customer_scope(*, email: str, customer_name: str):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name, billing_email=email)
    CustomerMembership.objects.create(customer=customer, user=user)
    return user, customer


def create_order(customer, actor):
    service = CatalogService.objects.create(
        code=f"dtf-{customer.name.lower()}",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
    )
    order = Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="25.00",
        total_amount="25.00",
    )
    order.items.create(
        service=service,
        position=1,
        service_code=service.code,
        service_name=service.name,
        service_type=service.service_type,
        unit=service.unit,
        quantity="2.00",
        unit_price="12.50",
        line_total="25.00",
    )
    return order


class FakePayPalGateway:
    def __init__(self, *, fail_create: bool = False, fail_capture: bool = False):
        self.fail_create = fail_create
        self.fail_capture = fail_capture
        self.counter = 0

    def create_order(self, *, order):
        if self.fail_create:
            from apps.billing.services.paypal import PayPalAPIError

            raise PayPalAPIError("PayPal unavailable.")
        self.counter += 1
        return type(
            "CreateResult",
            (),
            {
                "paypal_order_id": f"PP-ORDER-{order.public_id.hex[:8]}-{self.counter}",
                "status": "APPROVED",
                "approval_url": "https://paypal.test/approve/123",
                "payload": {"id": "dummy", "status": "APPROVED"},
            },
        )()

    def capture_order(self, *, paypal_order_id: str):
        if self.fail_capture:
            from apps.billing.services.paypal import PayPalAPIError

            raise PayPalAPIError("PayPal capture failed.")
        return type(
            "CaptureResult",
            (),
            {
                "capture_id": f"CAP-{paypal_order_id}",
                "status": "COMPLETED",
                "payload": {"id": paypal_order_id, "status": "COMPLETED"},
            },
        )()


def client_initiate_route(customer_public_id, order_public_id):
    return reverse(
        "billing:client-paypal-payment-initiate",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
        },
    )


def client_invoice_route(customer_public_id, order_public_id):
    return reverse(
        "billing:client-invoice-detail",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
        },
    )


def client_invoice_download_route(customer_public_id, order_public_id):
    return reverse(
        "billing:client-invoice-download",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
        },
    )


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_client_can_initiate_payment_on_own_order(monkeypatch):
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["status"] == Payment.Status.APPROVED
    assert payload["paypal_order_id"].startswith("PP-ORDER-")


@pytest.mark.django_db
def test_client_a_cannot_initiate_payment_for_customer_b(monkeypatch):
    user_a, customer_a = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    user_b, customer_b = create_customer_scope(email="client-b@example.com", customer_name="Acme B")
    _ = user_b
    order_b = create_order(customer_b, user_a)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user_a.email, password="pass") is True

    response = client.post(
        client_initiate_route(customer_b.public_id, order_b.public_id),
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Payment.objects.count() == 0
    assert customer_a.public_id != customer_b.public_id


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_client_can_read_invoice_after_valid_capture(monkeypatch):
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    initiate_response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )
    assert initiate_response.status_code == status.HTTP_201_CREATED
    paypal_order_id = initiate_response.json()["paypal_order_id"]

    backend_client = APIClient()
    capture_response = backend_client.post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="internal-token",
    )
    assert capture_response.status_code == status.HTTP_200_OK

    invoice_response = client.get(client_invoice_route(customer.public_id, order.public_id))
    assert invoice_response.status_code == status.HTTP_200_OK
    invoice_payload = invoice_response.json()
    assert invoice_payload["status"] == Invoice.Status.ISSUED
    assert invoice_payload["invoice_number"].startswith("INV-")
    assert invoice_payload["file"]["mime_type"] == "application/pdf"

    download = client.get(client_invoice_download_route(customer.public_id, order.public_id))
    assert download.status_code == status.HTTP_200_OK
    assert download["Content-Type"].startswith("application/pdf")
    body = b"".join(download.streaming_content)
    assert body[:4] == b"%PDF"


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_client_a_cannot_read_invoice_of_customer_b(monkeypatch):
    user_a, customer_a = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    user_b, customer_b = create_customer_scope(email="client-b@example.com", customer_name="Acme B")
    _ = user_b
    order_b = create_order(customer_b, user_a)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client_b = APIClient()
    assert client_b.login(email=user_b.email, password="pass") is True
    initiate_response = client_b.post(
        client_initiate_route(customer_b.public_id, order_b.public_id),
        {},
        format="json",
    )
    paypal_order_id = initiate_response.json()["paypal_order_id"]
    backend_client = APIClient()
    backend_client.post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order_b.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="internal-token",
    )

    client_a = APIClient()
    assert client_a.login(email=user_a.email, password="pass") is True
    forbidden = client_a.get(client_invoice_route(customer_b.public_id, order_b.public_id))
    not_found = client_a.get(client_invoice_route(customer_a.public_id, order_b.public_id))

    assert forbidden.status_code == status.HTTP_403_FORBIDDEN
    assert not_found.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_client_is_refused_on_staff_billing_route():
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    response = client.get(
        reverse("billing:staff-billing-detail", kwargs={"order_public_id": order.public_id})
    )

    assert_private_response_denied(response)


@pytest.mark.django_db
def test_staff_without_billing_permissions_is_refused():
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    customer = Customer.objects.create(name="Acme")
    order = create_order(customer, staff_user)
    client = APIClient()
    assert client.login(email=staff_user.email, password="pass") is True

    response = client.get(
        reverse("billing:staff-billing-detail", kwargs={"order_public_id": order.public_id})
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_paypal_error_is_mapped_to_failed_status(monkeypatch):
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway(fail_create=True)),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == ["PayPal unavailable."]
    payment = Payment.objects.get(order=order)
    assert payment.status == Payment.Status.FAILED


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_backend_capture_rejects_missing_internal_token(monkeypatch):
    cache.clear()
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True
    initiate_response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )
    paypal_order_id = initiate_response.json()["paypal_order_id"]

    backend_client = APIClient()
    response = backend_client.post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    audit_entry = AuditLogEntry.objects.get(action="security.paypal_internal_capture_denied")
    assert audit_entry.status == AuditLogEntry.Status.FAILURE
    assert audit_entry.metadata["reason"] == "missing_provided_token"


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_backend_capture_rejects_invalid_internal_token_and_audits(monkeypatch):
    cache.clear()
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True
    initiate_response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )
    paypal_order_id = initiate_response.json()["paypal_order_id"]

    backend_client = APIClient()
    response = backend_client.post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="wrong-token",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    audit_entry = AuditLogEntry.objects.get(action="security.paypal_internal_capture_denied")
    assert audit_entry.status == AuditLogEntry.Status.FAILURE
    assert audit_entry.metadata["reason"] == "invalid_token"


@pytest.mark.django_db
@override_settings(
    PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token",
    PAYPAL_INTERNAL_CONFIRM_RATE_LIMIT_MAX_ATTEMPTS=2,
    PAYPAL_INTERNAL_CONFIRM_RATE_LIMIT_WINDOW_SECONDS=60,
)
def test_backend_capture_rate_limits_repeated_invalid_token_attempts(monkeypatch):
    cache.clear()
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True
    initiate_response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )
    paypal_order_id = initiate_response.json()["paypal_order_id"]

    backend_client = APIClient()
    route = reverse("billing:backend-paypal-capture")
    for _ in range(2):
        response = backend_client.post(
            route,
            {
                "order_public_id": str(order.public_id),
                "paypal_order_id": paypal_order_id,
            },
            format="json",
            HTTP_X_INTERNAL_TOKEN="wrong-token",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    throttled = backend_client.post(
        route,
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="wrong-token",
    )

    assert throttled.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert throttled.json()["detail"] == ["Too many invalid confirmation attempts."]
    assert (
        AuditLogEntry.objects.filter(
            action="security.paypal_internal_capture_denied",
            status=AuditLogEntry.Status.FAILURE,
        ).count()
        == 3
    )
    assert (
        AuditLogEntry.objects.filter(
            action="security.paypal_internal_capture_rate_limited",
            status=AuditLogEntry.Status.FAILURE,
        ).count()
        == 1
    )


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_invoice_is_generated_once_with_idempotent_capture(monkeypatch):
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True
    initiate_response = client.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )
    paypal_order_id = initiate_response.json()["paypal_order_id"]

    backend_client = APIClient()
    first_capture = backend_client.post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="internal-token",
    )
    second_capture = backend_client.post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="internal-token",
    )

    assert first_capture.status_code == status.HTTP_200_OK
    assert second_capture.status_code == status.HTTP_200_OK
    assert Payment.objects.filter(order=order, status=Payment.Status.CAPTURED).count() == 1
    assert Invoice.objects.filter(order=order).count() == 1


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_staff_with_permissions_can_read_payment_and_invoice(monkeypatch):
    staff_user = get_user_model().objects.create_user(
        email="staff@example.com",
        password="pass",
        is_staff=True,
    )
    staff_user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="view_payment"),
        Permission.objects.get(codename="view_invoice"),
    )
    user, customer = create_customer_scope(email="client-a@example.com", customer_name="Acme A")
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakePayPalGateway()),
    )
    client_user = APIClient()
    assert client_user.login(email=user.email, password="pass") is True
    initiate_response = client_user.post(
        client_initiate_route(customer.public_id, order.public_id),
        {},
        format="json",
    )
    paypal_order_id = initiate_response.json()["paypal_order_id"]
    APIClient().post(
        reverse("billing:backend-paypal-capture"),
        {
            "order_public_id": str(order.public_id),
            "paypal_order_id": paypal_order_id,
        },
        format="json",
        HTTP_X_INTERNAL_TOKEN="internal-token",
    )

    staff_client = APIClient()
    assert staff_client.login(email=staff_user.email, password="pass") is True
    response = staff_client.get(
        reverse("billing:staff-billing-detail", kwargs={"order_public_id": order.public_id})
    )

    assert response.status_code == status.HTTP_200_OK
    payload = response.json()
    assert payload["payment"]["status"] == Payment.Status.CAPTURED
    assert payload["invoice"]["status"] == Invoice.Status.ISSUED
