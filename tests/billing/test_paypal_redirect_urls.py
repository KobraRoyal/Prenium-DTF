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
