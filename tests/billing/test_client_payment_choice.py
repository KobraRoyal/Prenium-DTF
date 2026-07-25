import pytest
from apps.billing.models import Payment
from apps.billing.services.gateways import configured_online_providers, resolve_online_provider
from apps.customers.models import Customer
from django.core.exceptions import ValidationError
from django.test import override_settings


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    STRIPE_SECRET_KEY="sk_test_x",
)
def test_client_can_choose_among_installed_providers():
    customer = Customer.objects.create(
        name="Chooser",
        preferred_settlement_method=Customer.PreferredSettlementMethod.WIRE_TRANSFER,
    )
    assert configured_online_providers() == [
        Payment.Provider.PAYPAL,
        Payment.Provider.STRIPE,
    ]
    assert (
        resolve_online_provider(customer=customer, requested_provider="stripe")
        == Payment.Provider.STRIPE
    )
    assert (
        resolve_online_provider(customer=customer, requested_provider="paypal")
        == Payment.Provider.PAYPAL
    )


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    STRIPE_SECRET_KEY="sk_test_x",
)
def test_uninstalled_provider_is_rejected():
    customer = Customer.objects.create(name="Stripe Only")
    with pytest.raises(ValidationError, match="pas disponible"):
        resolve_online_provider(customer=customer, requested_provider="paypal")
    assert (
        resolve_online_provider(customer=customer, requested_provider="stripe")
        == Payment.Provider.STRIPE
    )


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    STRIPE_SECRET_KEY="sk_test_x",
)
def test_missing_choice_requires_explicit_provider_when_several_installed():
    customer = Customer.objects.create(
        name="No Pref",
        preferred_settlement_method=Customer.PreferredSettlementMethod.WIRE_TRANSFER,
    )
    with pytest.raises(ValidationError, match="Choisissez"):
        resolve_online_provider(customer=customer, requested_provider=None)
