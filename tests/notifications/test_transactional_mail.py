from unittest.mock import patch

import pytest
from apps.billing.services.payments import PaymentService
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.notifications.services.transactional import schedule_order_created_email
from apps.notifications.tasks import send_order_created_email_task
from apps.orders.services.orders import OrderService
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase

from tests.billing.test_billing_api import FakePayPalGateway, create_customer_scope, create_order


@pytest.mark.django_db
def test_order_created_sends_transactional_email():
    user = get_user_model().objects.create_user(email="owner@example.com", password="pass")
    customer = Customer.objects.create(name="Acme", billing_email="billing@example.com")
    CustomerMembership.objects.create(customer=customer, user=user)
    dtf_service = CatalogService.objects.create(
        code="dtf-meter",
        name="DTF au metre",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="12.50",
        display_order=1,
    )

    mail.outbox.clear()
    with TestCase.captureOnCommitCallbacks(execute=True):
        OrderService().create_order(
            customer=customer,
            actor=user,
            items=[{"service_public_id": str(dtf_service.public_id), "quantity": "1.00"}],
        )

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert user.email in msg.to or "billing@example.com" in msg.to
    assert "Commande reçue" in msg.subject


@pytest.mark.django_db
def test_payment_captured_sends_transactional_email():
    user, customer = create_customer_scope(email="pay@example.com", customer_name="PayCo")
    order = create_order(customer, user)
    gateway = FakePayPalGateway()
    svc = PaymentService(gateway=gateway)
    _, payment = svc.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
    )
    assert payment is not None

    mail.outbox.clear()
    with TestCase.captureOnCommitCallbacks(execute=True):
        svc.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            payment_public_id=payment.public_id,
            actor=user,
            source="test",
        )

    assert len(mail.outbox) == 1
    assert "Paiement confirmé" in mail.outbox[0].subject


@pytest.mark.django_db
def test_confirm_capture_idempotent_does_not_send_duplicate_email():
    user, customer = create_customer_scope(email="idemp@example.com", customer_name="Idemp")
    order = create_order(customer, user)
    gateway = FakePayPalGateway()
    svc = PaymentService(gateway=gateway)
    _, payment = svc.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
    )
    with TestCase.captureOnCommitCallbacks(execute=True):
        svc.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            payment_public_id=payment.public_id,
            actor=user,
            source="test",
        )
    mail.outbox.clear()
    with TestCase.captureOnCommitCallbacks(execute=True):
        svc.confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id=payment.paypal_order_id,
            payment_public_id=payment.public_id,
            actor=user,
            source="test",
        )
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_order_created_email_is_dispatched_after_commit():
    with patch("apps.notifications.tasks.send_order_created_email_task.delay") as task_delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            schedule_order_created_email(
                order_public_id="b52bdab3-6877-45e8-a825-5f1720aa01bf",
            )

    task_delay.assert_called_once_with("b52bdab3-6877-45e8-a825-5f1720aa01bf")


@pytest.mark.django_db
def test_transactional_email_task_propagates_delivery_error():
    user = get_user_model().objects.create_user(email="retry@example.com", password="pass")
    customer = Customer.objects.create(name="Retry", billing_email="retry@example.com")
    order = create_order(customer, user)
    with patch(
        "apps.notifications.services.transactional.send_mail",
        side_effect=ConnectionError("SMTP unavailable"),
    ):
        with pytest.raises(ConnectionError, match="SMTP unavailable"):
            send_order_created_email_task.run(str(order.public_id))
