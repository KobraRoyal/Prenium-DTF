import pytest
from apps.billing.services.gateways import PaymentGatewayError, validate_provider_checkout_url


@pytest.mark.parametrize(
    "url",
    [
        "http://checkout.stripe.com/pay/cs_test",
        "https://checkout.stripe.com.evil.test/pay/cs_test",
        "https://evil.test/?next=https://checkout.stripe.com/pay/cs_test",
        "https://checkout.stripe.com:444/pay/cs_test",
        "https://checkout.stripe.com:invalid/pay/cs_test",
        "https://user@checkout.stripe.com/pay/cs_test",
    ],
)
def test_checkout_url_rejects_untrusted_stripe_origins(url):
    with pytest.raises(PaymentGatewayError, match="URL de paiement Stripe invalide"):
        validate_provider_checkout_url(
            url=url,
            provider="Stripe",
            allowed_hosts={"checkout.stripe.com"},
        )


def test_checkout_url_accepts_exact_provider_origin():
    url = "https://checkout.stripe.com/c/pay/cs_test"
    assert (
        validate_provider_checkout_url(
            url=url,
            provider="Stripe",
            allowed_hosts={"checkout.stripe.com"},
        )
        == url
    )
