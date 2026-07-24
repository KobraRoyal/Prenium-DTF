import hashlib
import hmac
import json
import time

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing import views as billing_views
from apps.billing.models import Invoice, Payment
from apps.billing.services.payments import PaymentService
from apps.customers.models import Customer
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
    assert payment.stripe_payment_intent_id == "pi_test_captured"
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
