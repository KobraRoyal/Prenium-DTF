from unittest.mock import patch

from apps.billing.services.paypal import PayPalGateway


def test_paypal_sanitize_strips_stripe_checkout_placeholder():
    dirty = (
        "http://localhost:8080/client/orders/x/payments/return/"
        "?status=success&session_id={{CHECKOUT_SESSION_ID}}"
    )
    cleaned = PayPalGateway._sanitize_redirect_url(dirty)
    assert "{{" not in cleaned
    assert "CHECKOUT_SESSION_ID" not in cleaned
    assert "status=success" in cleaned


def test_paypal_sanitize_keeps_clean_url():
    clean = "http://localhost:8080/client/orders/x/payments/return/?status=cancel"
    assert PayPalGateway._sanitize_redirect_url(clean) == clean


def test_paypal_capture_summary_extracts_captured_total_and_currency():
    capture_id, amount_total_cents, currency = PayPalGateway._capture_summary(
        {
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": "CAPTURE-123",
                                "amount": {"value": "167.70", "currency_code": "EUR"},
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert capture_id == "CAPTURE-123"
    assert amount_total_cents == 16770
    assert currency == "EUR"


def test_paypal_post_request_sends_idempotency_header():
    gateway = object.__new__(PayPalGateway)
    gateway.timeout_seconds = 5

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"id":"PAYPAL-ORDER-123"}'

    request_id = "123e4567-e89b-12d3-a456-426655440010"
    with patch("apps.billing.services.paypal.request.urlopen", return_value=Response()) as urlopen:
        payload = gateway._request_json(
            method="POST",
            url="https://api-m.sandbox.paypal.com/v2/checkout/orders",
            payload={"intent": "CAPTURE"},
            access_token="access-token",
            idempotency_key=request_id,
        )

    sent_request = urlopen.call_args.args[0]
    headers = {key.lower(): value for key, value in sent_request.header_items()}
    assert payload["id"] == "PAYPAL-ORDER-123"
    assert headers["paypal-request-id"] == request_id
