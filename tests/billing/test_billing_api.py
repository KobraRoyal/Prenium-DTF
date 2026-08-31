from threading import Barrier, Thread
from time import sleep

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
from django.core.exceptions import ValidationError
from django.db import (
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
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


def create_customer_owner_scope(*, email: str, customer_name: str):
    user, customer = create_customer_scope(email=email, customer_name=customer_name)
    CustomerMembership.objects.filter(customer=customer, user=user).update(
        role=CustomerMembership.Role.OWNER
    )
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
    provider = "paypal"

    def __init__(
        self,
        *,
        fail_create: bool = False,
        fail_capture: bool = False,
        capture_amount_cents: int = 2500,
        capture_currency: str = "EUR",
        capture_id: str | None = None,
    ):
        self.fail_create = fail_create
        self.fail_capture = fail_capture
        self.capture_amount_cents = capture_amount_cents
        self.capture_currency = capture_currency
        self.capture_id = capture_id
        self.counter = 0
        self.create_idempotency_keys: list[str] = []
        self.capture_idempotency_keys: list[str] = []

    def create_checkout(
        self,
        *,
        order,
        success_url: str = "",
        cancel_url: str = "",
        idempotency_key: str = "",
    ):
        self.create_idempotency_keys.append(idempotency_key)
        result = self.create_order(order=order)
        return type(
            "CheckoutCreateResult",
            (),
            {
                "provider_payment_id": result.paypal_order_id,
                "status": result.status,
                "checkout_url": result.approval_url,
                "payload": result.payload,
                "provider_capture_id": "",
            },
        )()

    def confirm_checkout(self, *, provider_payment_id: str, idempotency_key: str = ""):
        self.capture_idempotency_keys.append(idempotency_key)
        result = self.capture_order(paypal_order_id=provider_payment_id)
        return type(
            "CheckoutConfirmResult",
            (),
            {
                "provider_payment_id": provider_payment_id,
                "provider_capture_id": result.capture_id,
                "status": result.status,
                "payload": result.payload,
                "amount_total_cents": self.capture_amount_cents,
                "currency": self.capture_currency,
            },
        )()

    def create_order(self, *, order, return_url: str = "", cancel_url: str = ""):
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
                "capture_id": (
                    self.capture_id if self.capture_id is not None else f"CAP-{paypal_order_id}"
                ),
                "status": "COMPLETED",
                "payload": {"id": paypal_order_id, "status": "COMPLETED"},
            },
        )()


class FakeStripeGateway:
    provider = "stripe"

    def __init__(
        self,
        *,
        fail_create: bool = False,
        fail_confirm: bool = False,
        capture_amount_cents: int = 2500,
        capture_currency: str = "EUR",
        capture_id: str | None = None,
    ):
        self.fail_create = fail_create
        self.fail_confirm = fail_confirm
        self.capture_amount_cents = capture_amount_cents
        self.capture_currency = capture_currency
        self.capture_id = capture_id
        self.counter = 0

    def create_checkout(
        self,
        *,
        order,
        success_url: str = "",
        cancel_url: str = "",
        idempotency_key: str = "",
    ):
        _ = idempotency_key
        if self.fail_create:
            from apps.billing.services.stripe_gateway import StripeAPIError

            raise StripeAPIError("Stripe unavailable.")
        self.counter += 1
        session_id = f"cs_test_{order.public_id.hex[:8]}_{self.counter}"
        return type(
            "CheckoutCreateResult",
            (),
            {
                "provider_payment_id": session_id,
                "status": "open",
                "checkout_url": f"https://checkout.stripe.test/pay/{session_id}",
                "payload": {
                    "id": session_id,
                    "status": "open",
                    "url": f"https://checkout.stripe.test/pay/{session_id}",
                },
                "provider_capture_id": f"pi_{order.public_id.hex[:8]}",
            },
        )()

    def confirm_checkout(self, *, provider_payment_id: str, idempotency_key: str = ""):
        _ = idempotency_key
        if self.fail_confirm:
            from apps.billing.services.stripe_gateway import StripeAPIError

            raise StripeAPIError("Stripe confirm failed.")
        capture_id = (
            self.capture_id if self.capture_id is not None else f"pi_from_{provider_payment_id}"
        )
        return type(
            "CheckoutConfirmResult",
            (),
            {
                "provider_payment_id": provider_payment_id,
                "provider_capture_id": capture_id,
                "status": "COMPLETED",
                "payload": {
                    "id": provider_payment_id,
                    "payment_status": "paid",
                    "status": "complete",
                    "payment_intent": capture_id,
                },
                "amount_total_cents": self.capture_amount_cents,
                "currency": self.capture_currency,
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


def client_online_initiate_route(customer_public_id, order_public_id):
    return reverse(
        "billing:client-payment-initiate",
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
@pytest.mark.parametrize(
    "route_builder",
    [client_initiate_route, client_online_initiate_route],
)
@pytest.mark.parametrize(
    "role",
    [CustomerMembership.Role.MEMBER, CustomerMembership.Role.READONLY],
)
def test_payment_initiation_api_requires_customer_owner(route_builder, role):
    user, customer = create_customer_scope(
        email=f"payment-{role}-{route_builder.__name__}@example.com",
        customer_name=f"Payment {role}",
    )
    CustomerMembership.objects.filter(customer=customer, user=user).update(role=role)
    order = create_order(customer, user)
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    response = client.post(
        route_builder(customer.public_id, order.public_id),
        {"provider": Payment.Provider.PAYPAL},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Payment.objects.filter(order=order).count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize(
    "route_builder",
    [client_initiate_route, client_online_initiate_route],
)
def test_payment_initiation_api_enforces_csrf_for_owner(route_builder):
    user, customer = create_customer_owner_scope(
        email=f"payment-csrf-{route_builder.__name__}@example.com",
        customer_name="Payment CSRF",
    )
    order = create_order(customer, user)
    client = APIClient(enforce_csrf_checks=True)
    assert client.login(email=user.email, password="pass") is True

    response = client.post(
        route_builder(customer.public_id, order.public_id),
        {"provider": Payment.Provider.PAYPAL},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Payment.objects.filter(order=order).count() == 0


@pytest.mark.django_db
@override_settings(PAYPAL_INTERNAL_CONFIRM_TOKEN="internal-token")
def test_client_can_read_invoice_after_valid_capture(monkeypatch):
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
    assert invoice_payload["invoice_number"].startswith("JP-")
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
    user_b, customer_b = create_customer_owner_scope(
        email="client-b@example.com", customer_name="Acme B"
    )
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
def test_paypal_calls_use_distinct_idempotency_keys_per_operation():
    user, customer = create_customer_scope(
        email="paypal-idempotency@example.com",
        customer_name="PayPal Idempotency",
    )
    order = create_order(customer, user)
    gateway = FakePayPalGateway()
    service = PaymentService(gateway=gateway)

    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success",
        cancel_url="https://merchant.test/cancel",
    )
    service.confirm_capture(
        order_public_id=order.public_id,
        paypal_order_id=payment.paypal_order_id,
        actor=user,
        source="test",
    )

    assert len(gateway.create_idempotency_keys) == 1
    assert len(gateway.capture_idempotency_keys) == 1
    assert len(gateway.create_idempotency_keys[0]) == 36
    assert len(gateway.capture_idempotency_keys[0]) == 36
    assert gateway.create_idempotency_keys[0] != gateway.capture_idempotency_keys[0]


@pytest.mark.django_db
def test_repeated_paypal_initiation_reuses_same_attempt_and_provider_order():
    user, customer = create_customer_scope(
        email="paypal-reuse@example.com",
        customer_name="PayPal Reuse",
    )
    order = create_order(customer, user)
    gateway = FakePayPalGateway()
    service = PaymentService(gateway=gateway)
    kwargs = {
        "customer": customer,
        "order_public_id": order.public_id,
        "actor": user,
        "source": "test",
        "provider": Payment.Provider.PAYPAL,
        "success_url": "https://merchant.test/success",
        "cancel_url": "https://merchant.test/cancel",
    }

    _order, first = service.initiate_payment_for_customer_order(**kwargs)
    _order, second = service.initiate_payment_for_customer_order(**kwargs)

    assert first.pk == second.pk
    assert first.paypal_order_id == second.paypal_order_id
    assert Payment.objects.filter(order=order).count() == 1
    assert len(gateway.create_idempotency_keys) == 1
    assert AuditLogEntry.objects.filter(
        action="billing.payment_initiation_idempotent",
        target_public_id=first.public_id,
    ).exists()


@pytest.mark.django_db
def test_superseded_paypal_attempt_cannot_be_captured():
    user, customer = create_customer_scope(
        email="paypal-superseded@example.com",
        customer_name="PayPal Superseded",
    )
    order = create_order(customer, user)
    gateway = FakePayPalGateway()
    service = PaymentService(gateway=gateway)

    _order, first = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success-a",
        cancel_url="https://merchant.test/cancel-a",
    )
    _order, second = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success-b",
        cancel_url="https://merchant.test/cancel-b",
    )

    first.refresh_from_db()
    assert first.status == Payment.Status.CANCELLED
    with pytest.raises(ValidationError, match="n'est plus active"):
        service.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=first.paypal_order_id,
            actor=user,
            source="test",
        )
    assert gateway.capture_idempotency_keys == []

    service.confirm_capture(
        order_public_id=order.public_id,
        paypal_order_id=second.paypal_order_id,
        actor=user,
        source="test",
    )
    assert (
        Payment.objects.filter(
            order=order,
            status=Payment.Status.CAPTURED,
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_paypal_capture_rejects_repriced_order_before_provider_call():
    user, customer = create_customer_scope(
        email="paypal-repriced@example.com",
        customer_name="PayPal Repriced",
    )
    order = create_order(customer, user)
    gateway = FakePayPalGateway()
    service = PaymentService(gateway=gateway)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success",
        cancel_url="https://merchant.test/cancel",
    )
    order.total_amount = "30.00"
    order.save(update_fields=["total_amount", "updated_at"])

    with pytest.raises(ValidationError, match="a changé"):
        service.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            actor=user,
            source="test",
        )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.FAILED
    assert gateway.capture_idempotency_keys == []
    assert Invoice.objects.filter(order=order).count() == 0


@pytest.mark.django_db
def test_paypal_ambiguous_capture_error_retries_with_same_key():
    user, customer = create_customer_scope(
        email="paypal-retry-capture@example.com",
        customer_name="PayPal Retry Capture",
    )
    order = create_order(customer, user)
    gateway = FakePayPalGateway(fail_capture=True)
    service = PaymentService(gateway=gateway)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success",
        cancel_url="https://merchant.test/cancel",
    )

    with pytest.raises(ValidationError, match="capture failed"):
        service.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            actor=user,
            source="test",
        )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED
    assert payment.last_error_message == "PayPal capture failed."
    assert AuditLogEntry.objects.filter(
        action="billing.payment_capture_retryable",
        target_public_id=payment.public_id,
    ).exists()
    first_capture_key = gateway.capture_idempotency_keys[0]

    gateway.fail_capture = False
    _order, captured, _invoice = service.confirm_capture(
        order_public_id=order.public_id,
        paypal_order_id=payment.paypal_order_id,
        actor=user,
        source="test",
    )

    assert captured.status == Payment.Status.CAPTURED
    assert gateway.capture_idempotency_keys == [first_capture_key, first_capture_key]


@pytest.mark.django_db
def test_ambiguous_capture_cannot_be_replaced_by_another_checkout():
    user, customer = create_customer_scope(
        email="ambiguous-no-replacement@example.com",
        customer_name="Ambiguous No Replacement",
    )
    order = create_order(customer, user)

    class DebitedThenTimeoutGateway(FakePayPalGateway):
        def __init__(self):
            super().__init__()
            self.provider_debits: list[str] = []

        def capture_order(self, *, paypal_order_id: str):
            from apps.billing.services.paypal import PayPalAPIError

            self.provider_debits.append(paypal_order_id)
            raise PayPalAPIError("Timeout après débit provider.")

    paypal_gateway = DebitedThenTimeoutGateway()
    paypal_service = PaymentService(gateway=paypal_gateway)
    _order, payment = paypal_service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/paypal-success",
        cancel_url="https://merchant.test/paypal-cancel",
    )

    with pytest.raises(ValidationError, match="Timeout après débit"):
        paypal_service.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            actor=user,
            source="test",
        )

    payment.refresh_from_db()
    assert payment.capture_resolution_required is True
    stripe_gateway = FakeStripeGateway()
    stripe_service = PaymentService(gateway=stripe_gateway)
    with pytest.raises(ValidationError, match="confirmation.*indéterminée"):
        stripe_service.initiate_payment_for_customer_order(
            customer=customer,
            order_public_id=order.public_id,
            actor=user,
            source="test",
            provider=Payment.Provider.STRIPE,
            success_url="https://merchant.test/stripe-success",
            cancel_url="https://merchant.test/stripe-cancel",
        )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED
    assert paypal_gateway.provider_debits == [payment.paypal_order_id]
    assert stripe_gateway.counter == 0
    assert Payment.objects.filter(order=order).count() == 1
    assert AuditLogEntry.objects.filter(
        action="billing.payment_initiation_rejected",
        target_public_id=payment.public_id,
    ).exists()


@pytest.mark.django_db
def test_provider_capture_stays_durable_when_invoice_generation_fails():
    user, customer = create_customer_scope(
        email="capture-durable@example.com",
        customer_name="Capture Durable",
    )
    order = create_order(customer, user)

    class FailingInvoiceService:
        def ensure_invoice_for_captured_payment(self, **_kwargs):
            raise RuntimeError("PDF unavailable")

    service = PaymentService(
        gateway=FakePayPalGateway(),
        invoice_service=FailingInvoiceService(),
    )
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success",
        cancel_url="https://merchant.test/cancel",
    )

    with pytest.raises(RuntimeError, match="PDF unavailable"):
        service.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            actor=user,
            source="test",
        )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert payment.paypal_capture_id
    assert Invoice.objects.filter(order=order).count() == 0
    assert AuditLogEntry.objects.filter(
        action="billing.payment_captured",
        target_public_id=payment.public_id,
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("gateway_kwargs", "error_match"),
    [
        ({"capture_amount_cents": 2499}, "ne correspond pas"),
        ({"capture_currency": "USD"}, "ne correspond pas"),
        ({"capture_id": ""}, "identifiant de capture"),
    ],
)
def test_stripe_return_anomaly_requires_review_without_invoice(
    gateway_kwargs,
    error_match,
):
    user, customer = create_customer_scope(
        email="stripe-return-review@example.com",
        customer_name="Stripe Return Review",
    )
    order = create_order(customer, user)
    gateway = FakeStripeGateway(**gateway_kwargs)
    service = PaymentService(gateway=gateway)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="https://merchant.test/success",
        cancel_url="https://merchant.test/cancel",
    )

    with pytest.raises(ValidationError, match=error_match):
        service.confirm_capture(
            order_public_id=order.public_id,
            provider_payment_id=payment.stripe_checkout_session_id,
            expected_provider=Payment.Provider.STRIPE,
            actor=user,
            source="test",
        )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED_REVIEW
    assert Invoice.objects.filter(order=order).count() == 0
    assert AuditLogEntry.objects.filter(
        action="billing.payment_capture_review_required",
        target_public_id=payment.public_id,
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("gateway_kwargs", "error_match"),
    [
        ({"capture_amount_cents": 2499}, "ne correspond pas"),
        ({"capture_currency": "USD"}, "ne correspond pas"),
        ({"capture_id": ""}, "identifiant de capture"),
    ],
)
def test_paypal_capture_anomaly_requires_review_without_invoice_or_retry(
    monkeypatch,
    gateway_kwargs,
    error_match,
):
    from apps.billing.services.production_payment_gate import (
        order_awaits_client_payment,
        production_start_blocked_reason,
    )

    user, customer = create_customer_scope(
        email="paypal-mismatch@example.com",
        customer_name="PayPal Mismatch",
    )
    order = create_order(customer, user)
    order.billing_mode = Order.BillingMode.IMMEDIATE
    order.pricing_status = Order.PricingStatus.PRICED
    order.save(update_fields=["billing_mode", "pricing_status", "updated_at"])
    gateway = FakePayPalGateway(**gateway_kwargs)
    service = PaymentService(gateway=gateway)
    release_calls = []
    monkeypatch.setattr(
        service,
        "_release_production_after_payment",
        lambda **kwargs: release_calls.append(kwargs),
    )
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
        success_url="https://merchant.test/success",
        cancel_url="https://merchant.test/cancel",
    )

    with pytest.raises(ValidationError, match=error_match):
        service.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            actor=user,
            source="test",
        )

    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED_REVIEW
    assert Invoice.objects.filter(order=order).count() == 0
    assert release_calls == []
    order.refresh_from_db()
    monkeypatch.setattr(order, "uses_atelier_pricing", lambda: True)
    assert order_awaits_client_payment(order) is False
    assert production_start_blocked_reason(order) is not None
    with pytest.raises(ValidationError, match="déjà un règlement financier"):
        service.initiate_payment_for_customer_order(
            customer=customer,
            order_public_id=order.public_id,
            actor=user,
            source="test",
            provider=Payment.Provider.PAYPAL,
            success_url="https://merchant.test/success",
            cancel_url="https://merchant.test/cancel",
        )
    assert len(gateway.create_idempotency_keys) == 1


@pytest.mark.django_db
def test_database_rejects_two_financial_settlements_for_one_order():
    user, customer = create_customer_scope(
        email="single-settlement@example.com",
        customer_name="Single Settlement",
    )
    order = create_order(customer, user)
    Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.CAPTURED,
        amount=order.total_amount,
        currency=order.currency,
        paypal_order_id="PP-SINGLE-1",
        paypal_capture_id="CAP-SINGLE-1",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Payment.objects.create(
                order=order,
                provider=Payment.Provider.PAYPAL,
                status=Payment.Status.CAPTURED_REVIEW,
                amount=order.total_amount,
                currency=order.currency,
                paypal_order_id="PP-SINGLE-2",
                paypal_capture_id="CAP-SINGLE-2",
            )


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_paypal_initiation_creates_one_provider_order():
    if connection.vendor != "postgresql":
        pytest.skip("Le verrou select_for_update doit être validé avec PostgreSQL.")

    user, customer = create_customer_scope(
        email="paypal-concurrent@example.com",
        customer_name="PayPal Concurrent",
    )
    order = create_order(customer, user)

    class SlowGateway(FakePayPalGateway):
        def create_checkout(self, **kwargs):
            sleep(0.2)
            return super().create_checkout(**kwargs)

    gateway = SlowGateway()
    service = PaymentService(gateway=gateway)
    barrier = Barrier(2)
    payment_ids = []
    errors = []

    def initiate():
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            _order, payment = service.initiate_payment_for_customer_order(
                customer=customer,
                order_public_id=order.public_id,
                actor=user,
                source="concurrency_test",
                provider=Payment.Provider.PAYPAL,
                success_url="https://merchant.test/success",
                cancel_url="https://merchant.test/cancel",
            )
            payment_ids.append(payment.public_id)
        except Exception as exc:  # pragma: no cover - remonté par l'assertion principale
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [Thread(target=initiate), Thread(target=initiate)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(set(payment_ids)) == 1
    assert Payment.objects.filter(order=order).count() == 1
    assert len(gateway.create_idempotency_keys) == 1


@pytest.mark.django_db(transaction=True)
def test_postgres_concurrent_distinct_captures_call_paypal_once(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("Le verrou select_for_update doit être validé avec PostgreSQL.")

    from apps.billing.services import production_payment_gate
    from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService
    from apps.notifications.services import transactional

    user, customer = create_customer_scope(
        email="paypal-double-capture@example.com",
        customer_name="PayPal Double Capture",
    )
    order = create_order(customer, user)
    first = Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.APPROVED,
        amount=order.total_amount,
        currency=order.currency,
        paypal_order_id="PP-CONCURRENT-1",
        approval_url="https://paypal.test/approve/1",
    )
    second = Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.APPROVED,
        amount=order.total_amount,
        currency=order.currency,
        paypal_order_id="PP-CONCURRENT-2",
        approval_url="https://paypal.test/approve/2",
    )

    class SlowCaptureGateway(FakePayPalGateway):
        def confirm_checkout(self, **kwargs):
            sleep(0.2)
            return super().confirm_checkout(**kwargs)

    gateway = SlowCaptureGateway()
    service = PaymentService(gateway=gateway)
    monkeypatch.setattr(transactional, "schedule_payment_captured_email", lambda **_kwargs: None)
    monkeypatch.setattr(
        production_payment_gate,
        "should_defer_order_created_until_payment",
        lambda _order: False,
    )
    monkeypatch.setattr(
        CustomerVolumeDiscountTierService,
        "notify_immediate_tier_after_capture",
        lambda self, **_kwargs: None,
    )
    monkeypatch.setattr(
        service,
        "_release_production_after_payment",
        lambda **_kwargs: None,
    )
    barrier = Barrier(2)
    completed = []
    errors = []

    def capture(payment):
        close_old_connections()
        try:
            barrier.wait(timeout=5)
            _order, captured_payment, _invoice = service.confirm_capture(
                order_public_id=order.public_id,
                paypal_order_id=payment.paypal_order_id,
                expected_provider=Payment.Provider.PAYPAL,
                actor=user,
                source="concurrency_test",
            )
            completed.append(captured_payment.public_id)
        except ValidationError as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [
        Thread(target=capture, args=(first,)),
        Thread(target=capture, args=(second,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert len(completed) == 1
    assert len(errors) == 1
    assert "déjà un règlement financier" in str(errors[0])
    assert (
        Payment.objects.filter(
            order=order,
            status=Payment.Status.CAPTURED,
        ).count()
        == 1
    )
    assert len(gateway.capture_idempotency_keys) == 1


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
    user, customer = create_customer_owner_scope(
        email="client-a@example.com", customer_name="Acme A"
    )
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
