from pathlib import Path
from unittest.mock import patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing.models import Invoice, Payment
from apps.customers.models import CustomerMembership
from apps.orders.models import Order
from django.test import Client, override_settings
from django.urls import reverse

from tests.billing.test_billing_api import create_customer_scope, create_order


def create_owner_scope(*, email: str, customer_name: str):
    user, customer = create_customer_scope(email=email, customer_name=customer_name)
    CustomerMembership.objects.filter(customer=customer, user=user).update(
        role=CustomerMembership.Role.OWNER
    )
    return user, customer


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
    STRIPE_SECRET_KEY="",
    STRIPE_PUBLISHABLE_KEY="",
)
def test_paypal_initiate_returns_json_for_sdk_flow():
    user, customer = create_owner_scope(
        email="sdk-init@example.com",
        customer_name="SDK Init Co",
    )
    order = create_order(customer, user)
    order.billing_mode = Order.BillingMode.IMMEDIATE
    order.save(update_fields=["billing_mode", "updated_at"])
    client = Client()
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-initiate",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    with patch("apps.portal.views_payments.billing_service") as billing_service:
        billing_service.initiate_payment_for_customer_order.return_value = (
            order,
            Payment(
                provider=Payment.Provider.PAYPAL,
                approval_url="https://paypal.test/approve/sdk",
                paypal_order_id="PAYPAL-ORDER-123",
            ),
        )
        response = client.post(
            url,
            {"provider": "paypal", "sdk": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["paypal_order_id"] == "PAYPAL-ORDER-123"
    assert "approval_url" not in payload


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
def test_paypal_sdk_capture_returns_redirect_url():
    user, customer = create_owner_scope(
        email="sdk-capture@example.com",
        customer_name="SDK Capture Co",
    )
    order = create_order(customer, user)
    client = Client()
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-capture",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    with patch("apps.portal.views_payments.billing_service") as billing_service:
        billing_service.confirm_capture.return_value = (
            order,
            Payment(
                provider=Payment.Provider.PAYPAL,
                status=Payment.Status.CAPTURED,
                amount=order.total_amount,
                currency=order.currency,
            ),
            None,
        )
        response = client.post(
            url,
            {"paypal_order_id": "PAYPAL-ORDER-456"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["status"] == "captured"
    assert "panel=billing" in payload["redirect_url"]
    assert "paid=1" in payload["redirect_url"]
    billing_service.confirm_capture.assert_called_once_with(
        order_public_id=order.public_id,
        paypal_order_id="PAYPAL-ORDER-456",
        expected_provider=Payment.Provider.PAYPAL,
        actor=user,
        source="client_portal_sdk",
    )


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
def test_paypal_sdk_capture_rejects_cross_customer_access():
    user_a, customer_a = create_owner_scope(
        email="sdk-capture-a@example.com",
        customer_name="SDK Capture A",
    )
    user_b, customer_b = create_owner_scope(
        email="sdk-capture-b@example.com",
        customer_name="SDK Capture B",
    )
    _ = (customer_a, user_b)
    order_b = create_order(customer_b, user_b)
    client = Client()
    client.force_login(user_a)
    url = reverse(
        "portal:client-order-payment-capture",
        kwargs={
            "customer_public_id": customer_b.public_id,
            "order_public_id": order_b.public_id,
        },
    )

    with patch("apps.portal.views_payments.billing_service") as billing_service:
        response = client.post(
            url,
            {"paypal_order_id": "PAYPAL-ORDER-CROSS-TENANT"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    assert response.status_code == 403
    billing_service.confirm_capture.assert_not_called()


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
def test_paypal_sdk_capture_requires_customer_owner_role():
    user, customer = create_customer_scope(
        email="sdk-capture-member@example.com",
        customer_name="SDK Capture Member",
    )
    order = create_order(customer, user)
    client = Client()
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-capture",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )

    with patch("apps.portal.views_payments.billing_service") as billing_service:
        response = client.post(url, {"paypal_order_id": "PAYPAL-ORDER-MEMBER"})

    assert response.status_code == 403
    billing_service.confirm_capture.assert_not_called()


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
def test_paypal_sdk_capture_requires_csrf_token():
    user, customer = create_owner_scope(
        email="sdk-capture-csrf@example.com",
        customer_name="SDK Capture CSRF",
    )
    order = create_order(customer, user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-capture",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )

    with patch("apps.portal.views_payments.billing_service") as billing_service:
        response = client.post(url, {"paypal_order_id": "PAYPAL-ORDER-NO-CSRF"})

    assert response.status_code == 403
    billing_service.confirm_capture.assert_not_called()


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
@pytest.mark.parametrize("provider", [Payment.Provider.PAYPAL, Payment.Provider.STRIPE])
def test_paypal_sdk_capture_rejects_provider_id_not_owned_by_requested_order(provider):
    user, customer = create_owner_scope(
        email=f"sdk-capture-scope-{provider}@example.com",
        customer_name=f"SDK Capture Scope {provider}",
    )
    requested_order = create_order(customer, user)
    provider_order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount="25.00",
        total_amount="25.00",
    )
    provider_id = "PAYPAL-OTHER-ORDER" if provider == Payment.Provider.PAYPAL else "cs_other"
    Payment.objects.create(
        order=(provider_order if provider == Payment.Provider.PAYPAL else requested_order),
        provider=provider,
        status=Payment.Status.APPROVED,
        amount=provider_order.total_amount,
        currency=provider_order.currency,
        paypal_order_id=(provider_id if provider == Payment.Provider.PAYPAL else ""),
        stripe_checkout_session_id=(provider_id if provider == Payment.Provider.STRIPE else ""),
    )
    client = Client()
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-capture",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": requested_order.public_id,
        },
    )

    response = client.post(
        url,
        {"paypal_order_id": provider_id},
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_ACCEPT="application/json",
    )

    assert response.status_code == 404
    assert Invoice.objects.filter(order=requested_order).count() == 0


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
def test_paypal_popup_cancel_return_renders_postmessage_page():
    user, customer = create_owner_scope(
        email="popup-cancel@example.com",
        customer_name="Popup Cancel Co",
    )
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
        approval_url="https://paypal.test/approve/old",
        paypal_order_id="PAYPAL-CANCEL-EXACT",
    )
    client = Client()
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-return",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    response = client.get(f"{url}?status=cancel&popup=1&token={payment.paypal_order_id}")

    assert response.status_code == 200
    body = response.content.decode()
    assert "prenium-payment-return" in body
    assert "cancel" in body
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CANCELLED
    assert AuditLogEntry.objects.filter(
        action="billing.payment_cancelled",
        target_public_id=payment.public_id,
    ).exists()


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-test-id",
    PAYPAL_CLIENT_SECRET="paypal-test-secret",
)
def test_generic_cancel_get_does_not_mutate_payment():
    user, customer = create_owner_scope(
        email="generic-cancel@example.com",
        customer_name="Generic Cancel Co",
    )
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.APPROVED,
        amount=order.total_amount,
        currency=order.currency,
        paypal_order_id="PAYPAL-NOT-CANCELLED",
    )
    client = Client()
    client.force_login(user)
    url = reverse(
        "portal:client-order-payment-return",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )

    response = client.get(f"{url}?status=cancel&provider=paypal")

    assert response.status_code == 302
    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED


def test_paypal_sdk_keeps_standard_popup_enabled_and_uses_eligible_buttons():
    source = (
        Path(__file__).parents[2] / "backend" / "static_src" / "js" / "client-billing-pay.js"
    ).read_text(encoding="utf-8")

    assert "data-popups-disabled" not in source
    assert "paypal.Buttons(buildPayPalButtonOptions" in source
    assert "paypal.FUNDING.CARD" not in source
