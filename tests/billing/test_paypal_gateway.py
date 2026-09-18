import json

import pytest
from apps.billing import views as billing_views
from apps.billing.models import Invoice, Payment
from apps.billing.services.gateways import PaymentGatewayError
from apps.billing.services.payments import PaymentService
from apps.billing.services.paypal import PayPalAPIError, PayPalGateway
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from tests.billing.test_billing_api import FakePayPalGateway, create_customer_scope, create_order


@override_settings(PAYPAL_CLIENT_ID="paypal-id", PAYPAL_CLIENT_SECRET="paypal-secret")
def test_paypal_capture_treats_already_captured_as_success(monkeypatch):
    gateway = PayPalGateway()
    calls: list[str] = []

    def fake_request(*, method, url, payload, access_token, extra_headers=None):
        calls.append(method)
        if method == "POST" and str(url).endswith("/capture"):
            raise PayPalAPIError("UNPROCESSABLE_ENTITY ORDER_ALREADY_CAPTURED")
        return {
            "id": "ORDER1",
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "CAP1",
                                "status": "COMPLETED",
                                "amount": {"value": "25.00", "currency_code": "EUR"},
                            }
                        ]
                    }
                }
            ],
        }

    monkeypatch.setattr(gateway, "_get_access_token", lambda: "tok")
    monkeypatch.setattr(gateway, "_request_json", fake_request)
    result = gateway.capture_order(paypal_order_id="ORDER1")
    assert result.capture_id == "CAP1"
    assert result.status == "COMPLETED"
    assert calls == ["POST", "GET"]


@override_settings(PAYPAL_CLIENT_ID="paypal-id", PAYPAL_CLIENT_SECRET="paypal-secret")
def test_paypal_pending_capture_is_not_completed(monkeypatch):
    gateway = PayPalGateway()

    def fake_request(*, method, url, payload, access_token, extra_headers=None):
        return {
            "id": "ORDER2",
            "status": "COMPLETED",
            "purchase_units": [{"payments": {"captures": [{"id": "CAP2", "status": "PENDING"}]}}],
        }

    monkeypatch.setattr(gateway, "_get_access_token", lambda: "tok")
    monkeypatch.setattr(gateway, "_request_json", fake_request)
    result = gateway.capture_order(paypal_order_id="ORDER2")
    assert result.capture_id == "CAP2"
    assert result.status == "PENDING"


@override_settings(PAYPAL_CLIENT_ID="paypal-id", PAYPAL_CLIENT_SECRET="paypal-secret")
def test_paypal_create_order_sends_request_id(monkeypatch):
    gateway = PayPalGateway()
    captured = {}

    def fake_request(*, method, url, payload, access_token, extra_headers=None):
        captured["extra_headers"] = extra_headers
        return {
            "id": "ORDER-REQ",
            "status": "CREATED",
            "links": [{"rel": "approve", "href": "https://www.sandbox.paypal.com/approve"}],
        }

    class DummyOrder:
        public_id = type(
            "P", (), {"__str__": lambda self: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
        )()
        short_ref = "CMD-1"
        total_amount = "25.00"
        currency = "EUR"

    monkeypatch.setattr(gateway, "_get_access_token", lambda: "tok")
    monkeypatch.setattr(gateway, "_request_json", fake_request)
    result = gateway.create_order(order=DummyOrder(), request_id="pay-123")
    assert result.paypal_order_id == "ORDER-REQ"
    assert captured["extra_headers"] == {"PayPal-Request-Id": "pay-123"}


@override_settings(PAYPAL_CLIENT_ID="paypal-id", PAYPAL_CLIENT_SECRET="paypal-secret")
def test_paypal_rejects_untrusted_approval_url(monkeypatch):
    gateway = PayPalGateway()
    monkeypatch.setattr(gateway, "_get_access_token", lambda: "tok")
    monkeypatch.setattr(
        gateway,
        "_request_json",
        lambda **_kwargs: {
            "id": "ORDER-UNTRUSTED",
            "status": "CREATED",
            "links": [{"rel": "approve", "href": "https://www.paypal.com.evil.test/approve"}],
        },
    )
    order = type(
        "Order",
        (),
        {"public_id": "id", "short_ref": "REF", "total_amount": "1", "currency": "EUR"},
    )()
    with pytest.raises(PaymentGatewayError, match="URL de paiement PayPal invalide"):
        gateway.create_order(order=order)


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    PAYPAL_WEBHOOK_ID="wh-test",
)
def test_paypal_webhook_captures_approved_order(monkeypatch):
    user, customer = create_customer_scope(email="pp-wh@example.com", customer_name="PP WH")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakePayPalGateway())
    monkeypatch.setattr(billing_views, "payment_service", service)
    _order, payment = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.PAYPAL,
    )
    event = {
        "id": "WH-EVT-1",
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": payment.paypal_order_id},
    }

    def fake_verify(self, *, payload, headers):
        return json.loads(payload.decode())

    monkeypatch.setattr(PayPalGateway, "verify_and_parse_webhook", fake_verify)
    response = APIClient().post(
        reverse("billing:backend-paypal-webhook"),
        data=json.dumps(event).encode(),
        content_type="application/json",
        HTTP_PAYPAL_TRANSMISSION_ID="tx",
        HTTP_PAYPAL_TRANSMISSION_TIME="now",
        HTTP_PAYPAL_TRANSMISSION_SIG="sig",
        HTTP_PAYPAL_CERT_URL="https://paypal.test/cert",
        HTTP_PAYPAL_AUTH_ALGO="SHA256withRSA",
    )
    assert response.status_code == status.HTTP_200_OK
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert Invoice.objects.filter(order=order).exists()


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    PAYPAL_WEBHOOK_ID="wh-test",
)
def test_paypal_webhook_rejects_unverified_signature(monkeypatch):
    event = {"id": "WH-BAD", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {"id": "x"}}

    def fake_verify(self, *, payload, headers):
        raise PayPalAPIError("Invalid PayPal webhook signature.")

    monkeypatch.setattr(PayPalGateway, "verify_and_parse_webhook", fake_verify)
    response = APIClient().post(
        reverse("billing:backend-paypal-webhook"),
        data=json.dumps(event).encode(),
        content_type="application/json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
