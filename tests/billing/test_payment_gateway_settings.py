import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Payment, PaymentGatewaySettings
from apps.billing.services.gateway_settings import (
    mask_secret,
    payment_gateway_settings_service,
)
from apps.billing.services.gateways import configured_online_providers
from apps.billing.services.payments import PaymentService
from apps.customers.models import Customer, CustomerMembership
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from tests.billing.test_billing_api import FakeStripeGateway, create_customer_scope, create_order

FERNET_TEST_KEY = "v1:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="


def _permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _staff_user(*, email: str, view_gateways: bool = False, change_gateways: bool = False):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    user.user_permissions.add(_permission("accounts", "access_staff_portal"))
    if view_gateways:
        user.user_permissions.add(_permission("billing", "view_paymentgatewaysettings"))
    if change_gateways:
        user.user_permissions.add(_permission("billing", "change_paymentgatewaysettings"))
    return user


def _client_user(*, email: str, customer_name: str):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name=customer_name)
    CustomerMembership.objects.create(
        customer=customer,
        user=user,
        role=CustomerMembership.Role.OWNER,
    )
    return user


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    STRIPE_SECRET_KEY="sk_test_x",
)
def test_env_providers_remain_available_without_atelier_row():
    assert PaymentGatewaySettings.objects.count() == 0
    assert configured_online_providers() == [
        Payment.Provider.PAYPAL,
        Payment.Provider.STRIPE,
    ]


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id",
    PAYPAL_CLIENT_SECRET="paypal-secret",
    STRIPE_SECRET_KEY="sk_test_x",
    PAYMENT_SECRET_ENCRYPTION_KEYS=[FERNET_TEST_KEY],
)
def test_atelier_row_can_enable_one_provider_and_disable_the_other():
    manager = _staff_user(
        email="pay-admin@example.com",
        view_gateways=True,
        change_gateways=True,
    )
    payment_gateway_settings_service.update(
        paypal_enabled=False,
        stripe_enabled=True,
        paypal_client_id="",
        paypal_client_secret="",
        paypal_webhook_id="",
        stripe_publishable_key="",
        stripe_secret_key="",
        stripe_webhook_secret="",
        actor=manager,
        source="test",
    )
    assert configured_online_providers() == [Payment.Provider.STRIPE]


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    STRIPE_SECRET_KEY="",
    STRIPE_WEBHOOK_SECRET="",
    PAYMENT_SECRET_ENCRYPTION_KEYS=[FERNET_TEST_KEY],
)
def test_atelier_can_connect_stripe_from_encrypted_database_secret():
    manager = _staff_user(
        email="pay-db@example.com",
        view_gateways=True,
        change_gateways=True,
    )
    payment_gateway_settings_service.update(
        paypal_enabled=False,
        stripe_enabled=True,
        paypal_client_id="",
        paypal_client_secret="",
        paypal_webhook_id="",
        stripe_publishable_key="pk_test_visible",
        stripe_secret_key="sk_test_super_secret_value",
        stripe_webhook_secret="whsec_test_secret",
        actor=manager,
        source="test",
    )
    assert configured_online_providers() == [Payment.Provider.STRIPE]
    row = PaymentGatewaySettings.objects.get(singleton_key=1)
    assert "sk_test_super_secret_value" not in row.stripe_secret_key_encrypted
    snapshot = payment_gateway_settings_service.snapshot()
    assert snapshot.stripe_secret_hint.endswith("alue")
    assert "sk_test_super_secret_value" not in snapshot.stripe_secret_hint
    payment_gateway_settings_service.update(
        paypal_enabled=False,
        stripe_enabled=True,
        paypal_client_id="",
        paypal_client_secret="",
        paypal_webhook_id="",
        stripe_publishable_key="pk_test_visible",
        stripe_secret_key="",
        stripe_webhook_secret="",
        actor=manager,
        source="test",
    )
    assert payment_gateway_settings_service.effective().stripe_secret_key == (
        "sk_test_super_secret_value"
    )
    audit = AuditLogEntry.objects.filter(action="billing.payment_gateways.updated").last()
    assert audit is not None
    serialized = str(audit.metadata)
    assert "sk_test_super_secret_value" not in serialized
    assert "whsec_test_secret" not in serialized


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="",
    PAYPAL_CLIENT_SECRET="",
    STRIPE_SECRET_KEY="",
    PAYMENT_SECRET_ENCRYPTION_KEYS=[FERNET_TEST_KEY],
)
def test_enabling_provider_without_credentials_is_rejected():
    manager = _staff_user(
        email="pay-empty@example.com",
        view_gateways=True,
        change_gateways=True,
    )
    with pytest.raises(ValidationError):
        payment_gateway_settings_service.update(
            paypal_enabled=True,
            stripe_enabled=False,
            paypal_client_id="",
            paypal_client_secret="",
            paypal_webhook_id="",
            stripe_publishable_key="",
            stripe_secret_key="",
            stripe_webhook_secret="",
            actor=manager,
            source="test",
        )
    assert PaymentGatewaySettings.objects.count() == 0


@pytest.mark.django_db
def test_viewer_cannot_update_payment_gateways():
    viewer = _staff_user(email="pay-view@example.com", view_gateways=True)
    with pytest.raises(PermissionDenied):
        payment_gateway_settings_service.update(
            paypal_enabled=False,
            stripe_enabled=False,
            paypal_client_id="",
            paypal_client_secret="",
            paypal_webhook_id="",
            stripe_publishable_key="",
            stripe_secret_key="",
            stripe_webhook_secret="",
            actor=viewer,
            source="test",
        )


@pytest.mark.django_db
@override_settings(
    STRIPE_SECRET_KEY="sk_test_dummy",
    PAYMENT_SECRET_ENCRYPTION_KEYS=[FERNET_TEST_KEY],
)
def test_staff_payment_settings_route_is_isolated_and_masks_secrets():
    url = reverse("portal:staff-payment-settings")
    client_user = _client_user(email="pay-client@example.com", customer_name="Client pay")
    staff_without = _staff_user(email="pay-staff@example.com")
    viewer = _staff_user(email="pay-view-only@example.com", view_gateways=True)
    manager = _staff_user(
        email="pay-change@example.com",
        view_gateways=True,
        change_gateways=True,
    )
    client = APIClient()

    assert client.get(url).status_code == 302
    assert client.login(email=client_user.email, password="pass") is True
    assert client.get(url).status_code == 403
    client.logout()

    assert client.login(email=staff_without.email, password="pass") is True
    assert client.get(url).status_code == 403
    client.logout()

    assert client.login(email=viewer.email, password="pass") is True
    viewer_html = client.get(url).content.decode()
    assert "Paiements en ligne" in viewer_html
    assert "seul un administrateur Atelier" in viewer_html
    assert (
        client.post(
            url,
            {"paypal_enabled": "on", "stripe_enabled": "on"},
        ).status_code
        == 403
    )
    client.logout()

    assert client.login(email=manager.email, password="pass") is True
    response = client.post(
        url,
        {
            "stripe_enabled": "on",
            "stripe_secret_key": "sk_live_should_not_leak",
            "stripe_webhook_secret": "whsec_should_not_leak",
        },
        REMOTE_ADDR="192.0.2.44",
    )
    assert response.status_code == 302
    html = client.get(url).content.decode()
    assert "sk_live_should_not_leak" not in html
    assert "whsec_should_not_leak" not in html
    assert "••••" in html
    audit = AuditLogEntry.objects.get(action="billing.payment_gateways.updated")
    assert audit.ip_address == "192.0.2.44"
    assert "sk_live_should_not_leak" not in str(audit.metadata)


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_initiate_reuses_open_checkout_for_same_provider():
    user, customer = create_customer_scope(email="resume@example.com", customer_name="Resume")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    _order, first = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    _order, second = service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=Payment.Provider.STRIPE,
        success_url="http://localhost/success",
        cancel_url="http://localhost/cancel",
    )
    assert first is not None and second is not None
    assert first.pk == second.pk
    assert Payment.objects.filter(order=order).count() == 1
    assert service.gateway.counter == 1


def test_mask_secret_keeps_only_last_four_characters():
    assert mask_secret("") == ""
    assert mask_secret("abcd") == "••••"
    assert mask_secret("sk_test_1234") == "•••• 1234"


@pytest.mark.django_db
def test_payment_gateway_form_rejects_identical_paypal_id_and_secret():
    from apps.billing.forms import PaymentGatewaySettingsForm
    from apps.billing.services.gateway_settings import payment_gateway_settings_service

    snapshot = payment_gateway_settings_service.snapshot()
    form = PaymentGatewaySettingsForm(
        data={
            "paypal_enabled": True,
            "paypal_client_id": "same-value",
            "paypal_client_secret": "same-value",
            "paypal_webhook_id": "",
            "stripe_enabled": False,
            "stripe_publishable_key": "",
            "stripe_secret_key": "",
            "stripe_webhook_secret": "",
        },
        snapshot=snapshot,
    )
    assert not form.is_valid()
    assert "paypal_client_secret" in form.errors


@pytest.mark.django_db
def test_payment_gateway_form_rejects_swapped_stripe_keys():
    from apps.billing.forms import PaymentGatewaySettingsForm
    from apps.billing.services.gateway_settings import payment_gateway_settings_service

    snapshot = payment_gateway_settings_service.snapshot()
    form = PaymentGatewaySettingsForm(
        data={
            "paypal_enabled": False,
            "paypal_client_id": "",
            "paypal_client_secret": "",
            "paypal_webhook_id": "",
            "stripe_enabled": True,
            "stripe_publishable_key": "sk_test_secret_in_publishable_field",
            "stripe_secret_key": "pk_test_publishable_in_secret_field",
            "stripe_webhook_secret": "whsec_test",
        },
        snapshot=snapshot,
    )
    assert not form.is_valid()
    assert "stripe_publishable_key" in form.errors
    assert "stripe_secret_key" in form.errors


@pytest.mark.django_db
def test_payment_gateway_form_rejects_publishable_key_in_secret_field():
    from apps.billing.forms import PaymentGatewaySettingsForm
    from apps.billing.services.gateway_settings import payment_gateway_settings_service

    snapshot = payment_gateway_settings_service.snapshot()
    form = PaymentGatewaySettingsForm(
        data={
            "paypal_enabled": False,
            "paypal_client_id": "",
            "paypal_client_secret": "",
            "paypal_webhook_id": "",
            "stripe_enabled": True,
            "stripe_publishable_key": "pk_test_ok",
            "stripe_secret_key": "pk_test_wrong_field",
            "stripe_webhook_secret": "whsec_test",
        },
        snapshot=snapshot,
    )
    assert not form.is_valid()
    assert "stripe_secret_key" in form.errors
