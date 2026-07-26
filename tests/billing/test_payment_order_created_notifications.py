"""Notifications commande / paiement comptant CB."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from apps.billing.models import Payment
from apps.billing.services.payments import PaymentService
from apps.billing.services.production_payment_gate import should_defer_order_created_until_payment
from apps.catalog.models import CatalogService
from apps.customers.models import Customer, CustomerMembership
from apps.orders.models import Order
from apps.orders.services.orders import OrderService
from apps.uploads.models import OrderUpload, OrderUploadInspection
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.test import TestCase, override_settings


def _seed_catalog():
    CatalogService.objects.create(
        code="dtf-meter",
        name="DTF",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER,
        base_price="20.00",
        currency="EUR",
        display_order=1,
    )
    CatalogService.objects.create(
        code="file-prep",
        name="Prep",
        service_type=CatalogService.ServiceType.FILE_PREPARATION,
        unit=CatalogService.Unit.FIXED,
        base_price="5.00",
        currency="EUR",
        display_order=2,
    )


def _atelier_immediate_order(*, email="pay-notif@example.com"):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(
        name="Cash Notif",
        billing_email=email,
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    membership = CustomerMembership.objects.create(customer=customer, user=user)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.DRAFT,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PENDING,
        source="client_portal.b2b_checkout",
        currency="EUR",
        subtotal_amount=Decimal("0"),
        total_amount=Decimal("0"),
    )
    upload = OrderUpload(
        order=order,
        uploaded_by=user,
        original_filename="f.png",
        mime_type="image/png",
        size_bytes=8,
        quantity=1,
    )
    upload.file.save("f.png", ContentFile(b"fakebytes"), save=True)
    OrderUploadInspection.objects.create(
        order_upload=upload,
        status=OrderUploadInspection.Status.OK,
        image_width=1000,
        image_height=1000,
    )
    return user, customer, membership, order


@pytest.mark.django_db
def test_should_defer_order_created_for_immediate_atelier():
    _user, _customer, _membership, order = _atelier_immediate_order()
    assert should_defer_order_created_until_payment(order) is True


@pytest.mark.django_db
@override_settings(TRANSACTIONAL_EMAILS_ENABLED=True)
def test_b2b_submit_immediate_skips_order_created_email():
    _seed_catalog()
    user, customer, membership, order = _atelier_immediate_order(email="skip-created@example.com")
    with patch("apps.notifications.tasks.send_order_created_email_task.delay") as created_delay:
        with transaction.atomic():
            OrderService().submit_b2b_deferred_order(
                customer=customer,
                actor=user,
                customer_membership=membership,
                order_public_id=order.public_id,
                source="test",
                billing_mode="immediate",
            )
    assert created_delay.call_count == 0


@pytest.mark.django_db
@override_settings(TRANSACTIONAL_EMAILS_ENABLED=True)
def test_payment_capture_schedules_order_created_for_immediate_atelier():
    _seed_catalog()
    user, _customer, _membership, order = _atelier_immediate_order(email="after-pay@example.com")
    order.status = Order.Status.SUBMITTED
    order.pricing_status = Order.PricingStatus.PRICED
    order.subtotal_amount = Decimal("50.00")
    order.total_amount = Decimal("60.00")
    order.tax_amount = Decimal("10.00")
    order.save()

    payment = Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.APPROVED,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id="cs_test_notif",
        source="test",
    )

    service = PaymentService()
    with (
        patch("apps.notifications.tasks.send_payment_captured_email_task.delay") as pay_delay,
        patch("apps.notifications.tasks.send_order_created_email_task.delay") as created_delay,
    ):
        with TestCase.captureOnCommitCallbacks(execute=True):
            service._finalize_captured_payment(
                payment=payment,
                provider_capture_id="pi_test_notif",
                provider_payload={"ok": True},
                actor=user,
                source="test",
            )

    assert pay_delay.call_count == 1
    assert created_delay.call_count == 1
