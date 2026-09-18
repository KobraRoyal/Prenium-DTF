import hashlib
import hmac
import json
import time

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing import views as billing_views
from apps.billing.models import Invoice, Payment
from apps.billing.services.payments import PaymentService
from apps.billing.services.stripe_gateway import StripeGateway
from apps.customers.models import Customer
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.billing.test_billing_api import (
    FakeStripeGateway,
    client_online_initiate_route,
    create_customer_scope,
    create_order,
)


def _stripe_signature(*, payload: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = timestamp if timestamp is not None else int(time.time())
    signed = f"{ts}.".encode() + payload
    digest = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_stripe_checkout_accepts_only_card_for_immediate_payment(monkeypatch):
    user, customer = create_customer_scope(email="card-only@example.com", customer_name="Card")
    order = create_order(customer, user)
    gateway = StripeGateway()
    calls = []

    def checkout_response(**kwargs):
        calls.append(kwargs)
        return {
            "id": "cs_test_card_only",
            "status": "open",
            "url": "https://checkout.stripe.com/c/pay/cs_test_card_only",
        }

    monkeypatch.setattr(gateway, "_request_form", checkout_response)
    gateway.create_checkout(
        order=order,
        success_url="https://prenium.example.org/success",
        cancel_url="https://prenium.example.org/cancel",
        idempotency_key="attempt-id",
    )
    assert calls[0]["form"]["payment_method_types[0]"] == "card"


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", PUBLIC_BASE_URL="http://localhost:8080")
def test_client_can_initiate_stripe_payment(monkeypatch):
    user, customer = create_customer_scope(email="stripe-a@example.com", customer_name="Stripe A")
    customer.preferred_settlement_method = Customer.PreferredSettlementMethod.STRIPE
    customer.save(update_fields=["preferred_settlement_method", "updated_at"])
    order = create_order(customer, user)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakeStripeGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    response = client.post(
        client_online_initiate_route(customer.public_id, order.public_id),
        {"provider": "stripe"},
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    payload = response.json()
    assert payload["provider"] == Payment.Provider.STRIPE
    assert payload["stripe_checkout_session_id"].startswith("cs_test_")
    assert payload["checkout_url"].startswith("https://checkout.stripe.test/")
    assert Payment.objects.filter(provider=Payment.Provider.STRIPE).count() == 1


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_deferred_order_cannot_initiate_stripe(monkeypatch):
    user, customer = create_customer_scope(email="stripe-b@example.com", customer_name="Stripe B")
    customer.preferred_settlement_method = Customer.PreferredSettlementMethod.STRIPE
    customer.save(update_fields=["preferred_settlement_method", "updated_at"])
    order = create_order(customer, user)
    order.billing_mode = order.BillingMode.DEFERRED
    order.save(update_fields=["billing_mode", "updated_at"])
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakeStripeGateway()),
    )
    client = APIClient()
    assert client.login(email=user.email, password="pass") is True

    response = client.post(
        client_online_initiate_route(customer.public_id, order.public_id),
        {"provider": "stripe"},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert Payment.objects.count() == 0


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_WEBHOOK_SECRET="whsec_test",
)
def test_stripe_webhook_captures_and_creates_invoice(monkeypatch):
    user, customer = create_customer_scope(email="stripe-c@example.com", customer_name="Stripe C")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    monkeypatch.setattr(billing_views, "payment_service", service)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    assert payment is not None

    event = {
        "id": "evt_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "payment_status": "paid",
                "payment_intent": "pi_test_captured",
            }
        },
    }
    raw = json.dumps(event).encode()
    signature = _stripe_signature(payload=raw, secret="whsec_test")

    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=signature,
    )

    assert response.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert payment.stripe_payment_intent_id == f"pi_from_{payment.stripe_checkout_session_id}"
    assert Invoice.objects.filter(order=order).exists()
    assert AuditLogEntry.objects.filter(action="billing.payment_captured").exists()


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_WEBHOOK_SECRET="whsec_test",
)
def test_stripe_webhook_rejects_invalid_signature():
    event = {"id": "evt_bad", "type": "checkout.session.completed", "data": {"object": {}}}
    raw = json.dumps(event).encode()

    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="t=1,v1=deadbeef",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert AuditLogEntry.objects.filter(
        action="security.stripe_webhook_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_client_a_cannot_initiate_stripe_for_customer_b(monkeypatch):
    user_a, customer_a = create_customer_scope(email="stripe-x@example.com", customer_name="X")
    _user_b, customer_b = create_customer_scope(email="stripe-y@example.com", customer_name="Y")
    order_b = create_order(customer_b, user_a)
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakeStripeGateway()),
    )
    client = APIClient()
    assert client.login(email=user_a.email, password="pass") is True

    response = client.post(
        client_online_initiate_route(customer_b.public_id, order_b.public_id),
        {"provider": "stripe"},
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert Payment.objects.count() == 0
    assert customer_a.public_id != customer_b.public_id


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_WEBHOOK_SECRET="whsec_test",
)
def test_stripe_async_payment_succeeded_captures(monkeypatch):
    user, customer = create_customer_scope(email="stripe-async@example.com", customer_name="Async")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    monkeypatch.setattr(billing_views, "payment_service", service)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    event = {
        "id": "evt_async_1",
        "type": "checkout.session.async_payment_succeeded",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "payment_status": "paid",
                "payment_intent": "pi_async",
            }
        },
    }
    raw = json.dumps(event).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=raw, secret="whsec_test"),
    )
    assert response.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert Invoice.objects.filter(order=order).exists()


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_WEBHOOK_SECRET="whsec_test",
)
def test_stripe_unpaid_completed_webhook_does_not_fail_payment(monkeypatch):
    user, customer = create_customer_scope(
        email="stripe-unpaid@example.com", customer_name="Unpaid"
    )
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway(pending_confirm=True))
    monkeypatch.setattr(billing_views, "payment_service", service)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    event = {
        "id": "evt_unpaid_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": payment.stripe_checkout_session_id,
                "payment_status": "unpaid",
                "payment_intent": "pi_later",
            }
        },
    }
    raw = json.dumps(event).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=raw, secret="whsec_test"),
    )
    assert response.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    assert payment.status != Payment.Status.FAILED
    assert payment.status != Payment.Status.CAPTURED
    assert not Invoice.objects.filter(order=order).exists()


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_WEBHOOK_SECRET="whsec_test",
)
def test_stripe_async_payment_failed_keeps_unpaid_session_active(monkeypatch):
    user, customer = create_customer_scope(email="stripe-fail@example.com", customer_name="Fail")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway(pending_confirm=True))
    monkeypatch.setattr(billing_views, "payment_service", service)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    event = {
        "id": "evt_fail_1",
        "type": "checkout.session.async_payment_failed",
        "data": {"object": {"id": payment.stripe_checkout_session_id}},
    }
    raw = json.dumps(event).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=raw, secret="whsec_test"),
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["failed"] is False
    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED
    assert AuditLogEntry.objects.filter(
        action="billing.stripe_failure_pending_reconciliation"
    ).exists()
    with pytest.raises(ValidationError, match="vérification du règlement en cours"):
        service.initiate_payment_for_customer_order(
            customer=customer,
            order_public_id=order.public_id,
            actor=user,
            source="test_retry",
            provider=Payment.Provider.STRIPE,
        )
    assert Payment.objects.filter(order=order).count() == 1
    gateway = service.gateway
    gateway.pending_confirm = False
    success_event = {
        "id": "evt_after_failure",
        "type": "checkout.session.async_payment_succeeded",
        "data": {"object": {"id": payment.stripe_checkout_session_id}},
    }
    success_raw = json.dumps(success_event).encode()
    success = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=success_raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=success_raw, secret="whsec_test"),
    )
    assert success.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert Payment.objects.filter(order=order).count() == 1


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_stripe_failure_only_closes_expired_remote_session(monkeypatch):
    user, customer = create_customer_scope(
        email="stripe-expired-fail@example.com", customer_name="Fail"
    )
    order = create_order(customer, user)

    class ExpiredStripe(FakeStripeGateway):
        def confirm_checkout(self, *, provider_payment_id):
            result = super().confirm_checkout(provider_payment_id=provider_payment_id)
            result.status = "EXPIRED"
            return result

    service = PaymentService(gateway=ExpiredStripe())
    monkeypatch.setattr(billing_views, "payment_service", service)
    _, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    event = {
        "id": "evt_expired_fail",
        "type": "checkout.session.async_payment_failed",
        "data": {"object": {"id": payment.stripe_checkout_session_id}},
    }
    raw = json.dumps(event).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=raw, secret="whsec_test"),
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["failed"] is True
    payment.refresh_from_db()
    assert payment.status == Payment.Status.FAILED


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    STRIPE_WEBHOOK_SECRET="whsec_test",
)
def test_late_stripe_failure_event_uses_current_paid_session(monkeypatch):
    user, customer = create_customer_scope(
        email="stripe-late-fail@example.com", customer_name="Paid"
    )
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    monkeypatch.setattr(billing_views, "payment_service", service)
    _, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    event = {
        "id": "evt_late_failure",
        "type": "checkout.session.async_payment_failed",
        "data": {"object": {"id": payment.stripe_checkout_session_id}},
    }
    raw = json.dumps(event).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=raw, secret="whsec_test"),
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["failed"] is False
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert Invoice.objects.filter(order=order, payment=payment).exists()
    assert not AuditLogEntry.objects.filter(action="billing.payment_failed").exists()


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_stripe_failure_event_keeps_attempt_active_if_live_read_fails(monkeypatch):
    user, customer = create_customer_scope(
        email="stripe-read-fail@example.com", customer_name="Retry"
    )
    order = create_order(customer, user)

    class UnavailableStripe(FakeStripeGateway):
        def confirm_checkout(self, *, provider_payment_id):
            from apps.billing.services.stripe_gateway import StripeTransientError

            raise StripeTransientError("Stripe unavailable")

    service = PaymentService(gateway=UnavailableStripe())
    monkeypatch.setattr(billing_views, "payment_service", service)
    _, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    event = {
        "id": "evt_read_unavailable",
        "type": "checkout.session.async_payment_failed",
        "data": {"object": {"id": payment.stripe_checkout_session_id}},
    }
    raw = json.dumps(event).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=raw,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(payload=raw, secret="whsec_test"),
    )
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED
    assert not Invoice.objects.filter(order=order).exists()


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_stripe_pending_return_does_not_mark_failed():
    user, customer = create_customer_scope(
        email="stripe-pending@example.com", customer_name="Pending"
    )
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway(pending_confirm=True))
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    order, payment, invoice = service.confirm_capture(
        order_public_id=order.public_id,
        provider_payment_id=payment.stripe_checkout_session_id,
        actor=user,
        source="client_portal_return",
    )
    payment.refresh_from_db()
    assert payment.status != Payment.Status.FAILED
    assert payment.status != Payment.Status.CAPTURED
    assert invoice is None


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_stripe_amount_mismatch_is_rejected():
    user, customer = create_customer_scope(email="stripe-amt@example.com", customer_name="Amt")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway(amount_total_cents=1))
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    with pytest.raises(Exception, match="incohérent"):
        service.confirm_capture(
            order_public_id=order.public_id,
            provider_payment_id=payment.stripe_checkout_session_id,
            actor=user,
            source="test",
        )
    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED
    assert not Invoice.objects.filter(order=order).exists()


@override_settings(
    STRIPE_SECRET_KEY="sk_test_x",
    STRIPE_API_VERSION="2026-07-29.dahlia",
)
def test_stripe_requests_pin_api_version_and_idempotency_key(monkeypatch):
    from apps.billing.services.stripe_gateway import StripeGateway

    captured = {}

    class FakeResponse:
        def read(self):
            return json.dumps(
                {"id": "cs_test_headers", "status": "open", "url": "https://x"}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=None):
        captured["headers"] = {key.lower(): value for key, value in req.header_items()}
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("apps.billing.services.stripe_gateway.open_provider_request", fake_urlopen)
    gateway = StripeGateway()
    payload = gateway._request_form(
        method="POST",
        path="/v1/checkout/sessions",
        form={"mode": "payment"},
        idempotency_key="pay-public-id",
    )
    assert payload["id"] == "cs_test_headers"
    assert captured["headers"].get("stripe-version") == "2026-07-29.dahlia"
    assert captured["headers"].get("idempotency-key") == "pay-public-id"
    assert captured["headers"].get("authorization") == "Bearer sk_test_x"
