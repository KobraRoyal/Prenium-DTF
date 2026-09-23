import pytest
from apps.billing.models import Payment
from django.test import Client
from django.urls import reverse

from tests.billing.test_billing_api import FakePayPalGateway, create_customer_scope, create_order
from tests.billing.test_payment_readiness import _initiate


@pytest.mark.django_db
def test_cancel_fallback_redirects_to_portal_payment_return():
    user, customer = create_customer_scope(email="fallback-cancel@example.com", customer_name="FB")
    order = create_order(customer, user)
    from apps.billing.services.payments import PaymentService

    _, payment = _initiate(
        PaymentService(gateway=FakePayPalGateway()),
        customer=customer,
        order=order,
        user=user,
        provider=Payment.Provider.PAYPAL,
    )
    Payment.objects.filter(pk=payment.pk).update(paypal_order_id="PP-FALLBACK-CANCEL")

    client = Client()
    assert client.login(email="fallback-cancel@example.com", password="pass")
    response = client.get("/cancel?token=PP-FALLBACK-CANCEL")
    assert response.status_code == 302
    expected = reverse(
        "portal:client-order-payment-return",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    assert response["Location"].startswith(expected)
    assert "status=cancel" in response["Location"]
    assert "token=PP-FALLBACK-CANCEL" in response["Location"]


@pytest.mark.django_db
def test_ok_fallback_redirects_to_portal_payment_return():
    user, customer = create_customer_scope(email="fallback-ok@example.com", customer_name="FO")
    order = create_order(customer, user)
    from apps.billing.services.payments import PaymentService

    _, payment = _initiate(
        PaymentService(gateway=FakePayPalGateway()),
        customer=customer,
        order=order,
        user=user,
        provider=Payment.Provider.PAYPAL,
    )
    Payment.objects.filter(pk=payment.pk).update(paypal_order_id="PP-FALLBACK-OK")

    client = Client()
    assert client.login(email="fallback-ok@example.com", password="pass")
    response = client.get("/ok?token=PP-FALLBACK-OK")
    assert response.status_code == 302
    assert "status=success" in response["Location"]
    assert "token=PP-FALLBACK-OK" in response["Location"]
