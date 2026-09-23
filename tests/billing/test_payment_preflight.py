from datetime import timedelta
from io import StringIO
from urllib import error

import pytest
from apps.auditlog.services import record_event
from apps.billing.management.commands import payment_preflight
from apps.billing.models import Payment
from apps.billing.services.gateways import PaymentGatewayConfigurationError
from apps.billing.services.payments import STRIPE_FAILURE_RECONCILIATION_MESSAGE
from apps.billing.services.paypal import PayPalAPIError, PayPalConfigurationError, PayPalGateway
from apps.billing.services.stripe_gateway import StripeAPIError, StripeGateway
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.migrations.recorder import MigrationRecorder
from django.test import override_settings
from django.utils import timezone

from tests.billing.test_billing_api import create_customer_scope, create_order


@pytest.mark.django_db
def test_live_preflight_rejects_missing_webhooks_and_sandbox():
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="",
        STRIPE_SECRET_KEY="sk_test_fake",
        STRIPE_WEBHOOK_SECRET="",
        PUBLIC_BASE_URL="http://localhost:8080",
    ):
        with pytest.raises(CommandError, match="PAYPAL_WEBHOOK_ID"):
            call_command("payment_preflight", live=True)


@pytest.mark.django_db
def test_live_preflight_accepts_complete_live_configuration(monkeypatch):
    checked = []
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: checked.append("paypal"))
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: checked.append("stripe"))
    monkeypatch.setattr(
        payment_preflight,
        "probe_public_webhook_route",
        lambda url: checked.append(url) or True,
    )
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        output = StringIO()
        call_command("payment_preflight", live=True, stdout=output)
        assert "réussi" in output.getvalue()
        assert checked == [
            "paypal",
            "stripe",
            "https://prenium.example.org/api/backend/paypal/webhook/",
            "https://prenium.example.org/api/backend/stripe/webhook/",
        ]


@pytest.mark.django_db
def test_live_preflight_rejects_missing_public_webhook_route(monkeypatch):
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(
        payment_preflight,
        "probe_public_webhook_route",
        lambda url: "/paypal/" not in url,
    )
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        with pytest.raises(CommandError, match="Webhook paypal inaccessible"):
            call_command("payment_preflight", live=True)


@pytest.mark.parametrize(
    "status,allow,expected",
    [
        (405, "POST, OPTIONS", True),
        (405, "GET, OPTIONS", False),
        (404, "POST, OPTIONS", False),
    ],
)
def test_public_webhook_route_probe_requires_post_only_route(monkeypatch, status, allow, expected):
    def response(_request, *, timeout):
        assert timeout == 10
        raise error.HTTPError(
            "https://prenium.example.org/api/backend/paypal/webhook/",
            status,
            "probe",
            {"Allow": allow},
            None,
        )

    monkeypatch.setattr(payment_preflight, "open_provider_request", response)
    assert (
        payment_preflight.probe_public_webhook_route(
            "https://prenium.example.org/api/backend/paypal/webhook/"
        )
        is expected
    )


@pytest.mark.django_db
def test_live_preflight_rejects_provider_api_failure(monkeypatch):
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)

    def invalid_stripe_key(_self):
        raise StripeAPIError("Invalid API Key provided")

    monkeypatch.setattr(StripeGateway, "probe_readiness", invalid_stripe_key)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        with pytest.raises(CommandError, match="Stripe : vérification API échouée"):
            call_command("payment_preflight", live=True)


@pytest.mark.django_db
def test_live_preflight_rejects_unapplied_payment_constraint(monkeypatch):
    applied = MigrationRecorder.applied_migrations

    def without_payment_constraint(recorder):
        return set(applied(recorder)) - {("billing", "0011_payment_single_payable_or_captured")}

    monkeypatch.setattr(MigrationRecorder, "applied_migrations", without_payment_constraint)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        STRIPE_API_BASE_URL="https://api.stripe.com",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        with pytest.raises(CommandError, match="Migration billing.0011 non appliquée"):
            call_command("payment_preflight", live=True)


@pytest.mark.django_db
def test_live_preflight_rejects_faked_or_missing_unique_payment_index(monkeypatch):
    from django.db import connection

    get_constraints = connection.introspection.get_constraints

    def missing_payment_index(cursor, table_name):
        constraints = get_constraints(cursor, table_name)
        constraints.pop("uniq_payable_or_captured_payment_per_order", None)
        return constraints

    monkeypatch.setattr(connection.introspection, "get_constraints", missing_payment_index)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        STRIPE_API_BASE_URL="https://api.stripe.com",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        with pytest.raises(CommandError, match="Index unique"):
            call_command("payment_preflight", live=True)


@pytest.mark.django_db
def test_gateway_live_credentials_never_go_to_custom_api_hosts():
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_API_BASE_URL="https://paypal-proxy.example.com",
    ):
        with pytest.raises(PayPalConfigurationError, match="non officielle"):
            PayPalGateway()
    with override_settings(
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_API_BASE_URL="https://stripe-proxy.example.com",
    ):
        with pytest.raises(PaymentGatewayConfigurationError, match="non officielle"):
            StripeGateway()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "public_url,allowed_hosts",
    [
        ("https://127.0.0.2", ["127.0.0.2"]),
        ("https://[::1]", ["::1"]),
        ("https://10.0.0.8", ["10.0.0.8"]),
        ("https://atelier.local", ["atelier.local"]),
        ("https://prenium.example.org", ["localhost"]),
        ("https://prenium.example.org", ["*"]),
        ("https://prenium.example.org/chemin", ["prenium.example.org"]),
        ("https://prenium.example.org/?x=1", ["prenium.example.org"]),
        ("https://prenium.example.org/#fragment", ["prenium.example.org"]),
        ("https://prenium.example.org:bad", ["prenium.example.org"]),
        ("https://prenium.example.org:8443", ["prenium.example.org"]),
    ],
)
def test_live_preflight_rejects_unreachable_or_unallowed_public_host(
    monkeypatch, public_url, allowed_hosts
):
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: None)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        STRIPE_API_BASE_URL="https://api.stripe.com",
        PUBLIC_BASE_URL=public_url,
        ALLOWED_HOSTS=allowed_hosts,
    ):
        with pytest.raises(CommandError, match="PUBLIC_BASE_URL"):
            call_command("payment_preflight", live=True)


@pytest.mark.django_db
def test_gateway_readiness_probes_validate_responses(monkeypatch):
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        STRIPE_SECRET_KEY="sk_test_fake",
    ):
        paypal = PayPalGateway()
        stripe = StripeGateway()
    monkeypatch.setattr(paypal, "_get_access_token", lambda: "")
    with pytest.raises(PayPalAPIError, match="jeton"):
        paypal.probe_readiness()
    called = []
    monkeypatch.setattr(
        stripe,
        "_request_form",
        lambda **kwargs: called.append(kwargs) or {"data": []},
    )
    stripe.probe_readiness()
    assert called[0]["path"] == "/v1/checkout/sessions?limit=1"


@pytest.mark.django_db
def test_preflight_rejects_unknown_checkout_past_safe_retry_window():
    user, customer = create_customer_scope(email="old-idem@example.com", customer_name="Old")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=2))
    with pytest.raises(CommandError, match="hors fenêtre d'idempotence"):
        call_command("payment_preflight")


@pytest.mark.django_db
def test_preflight_rejects_unresolved_stripe_failure():
    user, customer = create_customer_scope(
        email="unresolved@example.com", customer_name="Unresolved"
    )
    order = create_order(customer, user)
    Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.APPROVED,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id="cs_unresolved",
        last_error_message=STRIPE_FAILURE_RECONCILIATION_MESSAGE,
    )
    with pytest.raises(CommandError, match="Échecs Stripe encore à rapprocher"):
        call_command("payment_preflight")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "local_status,remote_id,methods,remote_status,payment_status,error_message",
    [
        (Payment.Status.APPROVED, "", None, "", "", "sans référence distante"),
        (Payment.Status.FAILED, "", None, "", "", "historiques fermées sans référence"),
        (
            Payment.Status.APPROVED,
            "cs_historical",
            ["card", "sepa_debit"],
            "open",
            "unpaid",
            "moyens de paiement historiques",
        ),
        (Payment.Status.APPROVED, "cs_paid", ["card"], "complete", "paid", "état distant"),
        (Payment.Status.APPROVED, "cs_processing", ["card"], "complete", "unpaid", "état distant"),
        (Payment.Status.APPROVED, "cs_card", ["card"], "open", "unpaid", None),
        (Payment.Status.CANCELLED, "cs_old_open", ["card"], "open", "unpaid", "état distant"),
        (
            Payment.Status.CANCELLED,
            "cs_old_expired",
            ["card", "sepa_debit"],
            "expired",
            "unpaid",
            None,
        ),
    ],
)
def test_live_preflight_checks_active_stripe_sessions(
    monkeypatch, local_status, remote_id, methods, remote_status, payment_status, error_message
):
    user, customer = create_customer_scope(email="cutover@example.com", customer_name="Cutover")
    order = create_order(customer, user)
    Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=local_status,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id=remote_id,
    )
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(
        StripeGateway,
        "verify_checkout_binding",
        lambda _self, **_kwargs: {
            "payment_method_types": methods,
            "status": remote_status,
            "payment_status": payment_status,
        },
    )
    monkeypatch.setattr(payment_preflight, "probe_public_webhook_route", lambda _url: True)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        if error_message:
            with pytest.raises(CommandError, match=error_message):
                call_command("payment_preflight", live=True)
        else:
            call_command("payment_preflight", live=True, stdout=StringIO())


@pytest.mark.django_db
def test_live_preflight_accepts_audited_historical_stripe_attempt_without_reference(monkeypatch):
    user, customer = create_customer_scope(email="audited@example.com", customer_name="Audited")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CANCELLED,
        amount=order.total_amount,
        currency=order.currency,
    )
    record_event(action="billing.unknown_checkout_manually_closed", target=payment)
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(payment_preflight, "probe_public_webhook_route", lambda _url: True)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        call_command("payment_preflight", live=True, stdout=StringIO())


@pytest.mark.django_db
def test_live_preflight_scans_more_than_fifty_safe_historical_sessions(monkeypatch):
    user, customer = create_customer_scope(email="archive@example.com", customer_name="Archive")
    order = create_order(customer, user)
    Payment.objects.bulk_create(
        [
            Payment(
                order=order,
                provider=Payment.Provider.STRIPE,
                status=Payment.Status.CANCELLED,
                amount=order.total_amount,
                currency=order.currency,
                stripe_checkout_session_id=f"cs_old_{index}",
            )
            for index in range(51)
        ]
    )
    checked = []
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: None)

    def safe_expired(_self, **kwargs):
        checked.append(kwargs["provider_payment_id"])
        return {"status": "expired", "payment_status": "unpaid"}

    monkeypatch.setattr(StripeGateway, "verify_checkout_binding", safe_expired)
    monkeypatch.setattr(payment_preflight, "probe_public_webhook_route", lambda _url: True)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        call_command("payment_preflight", live=True, stdout=StringIO())
    assert len(checked) == 51


@pytest.mark.django_db
@pytest.mark.parametrize(
    "local_status,remote_id,remote_status,error_message",
    [
        (Payment.Status.APPROVED, "", "", "sans référence distante"),
        (Payment.Status.FAILED, "", "", "historiques fermées sans référence"),
        (Payment.Status.APPROVED, "PP-PAID", "COMPLETED", "état distant"),
        (Payment.Status.APPROVED, "PP-OPEN", "APPROVED", None),
        (Payment.Status.CANCELLED, "PP-OPEN", "APPROVED", "état distant"),
        (Payment.Status.CANCELLED, "PP-VOID", "VOIDED", None),
    ],
)
def test_live_preflight_checks_paypal_historical_orders(
    monkeypatch, local_status, remote_id, remote_status, error_message
):
    user, customer = create_customer_scope(
        email="paypal-cutover@example.com", customer_name="PayPal"
    )
    order = create_order(customer, user)
    Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=local_status,
        amount=order.total_amount,
        currency=order.currency,
        paypal_order_id=remote_id,
    )
    monkeypatch.setattr(PayPalGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(StripeGateway, "probe_readiness", lambda _self: None)
    monkeypatch.setattr(
        PayPalGateway,
        "verify_checkout_binding",
        lambda _self, **_kwargs: {"status": remote_status},
    )
    monkeypatch.setattr(payment_preflight, "probe_public_webhook_route", lambda _url: True)
    with override_settings(
        PAYPAL_CLIENT_ID="client",
        PAYPAL_CLIENT_SECRET="secret",
        PAYPAL_WEBHOOK_ID="webhook-id",
        PAYPAL_API_BASE_URL="https://api-m.paypal.com",
        STRIPE_SECRET_KEY="sk_live_fake",
        STRIPE_WEBHOOK_SECRET="whsec_fake",
        PUBLIC_BASE_URL="https://prenium.example.org",
        ALLOWED_HOSTS=["prenium.example.org"],
    ):
        if error_message:
            with pytest.raises(CommandError, match=error_message):
                call_command("payment_preflight", live=True)
        else:
            call_command("payment_preflight", live=True, stdout=StringIO())
