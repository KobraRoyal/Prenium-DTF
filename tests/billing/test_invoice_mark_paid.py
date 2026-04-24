from decimal import Decimal

import pytest
from apps.billing.models import Invoice, Payment
from apps.billing.services.invoices import InvoiceService
from apps.customers.models import Customer
from apps.orders.models import Order
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError


@pytest.mark.django_db
def test_mark_invoice_paid_sets_paid_at_and_actor():
    user = get_user_model().objects.create_user(email="ops@example.com", password="pass")
    customer = Customer.objects.create(name="WireCo", preferred_settlement_method="wire_transfer")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
    )
    invoice = Invoice.objects.create(
        order=order,
        status=Invoice.Status.ISSUED,
        invoice_number="INV-TEST-1",
        subtotal_amount=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        currency="EUR",
    )
    svc = InvoiceService()
    out = svc.mark_invoice_paid_by_staff(invoice=invoice, actor=user, source="test")
    assert out.paid_at is not None
    assert out.paid_recorded_by_id == user.id


@pytest.mark.django_db
def test_mark_invoice_paid_twice_raises():
    user = get_user_model().objects.create_user(email="ops2@example.com", password="pass")
    customer = Customer.objects.create(name="WireCo2")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"),
    )
    invoice = Invoice.objects.create(
        order=order,
        status=Invoice.Status.ISSUED,
        invoice_number="INV-TEST-2",
        subtotal_amount=Decimal("10.00"),
        total_amount=Decimal("10.00"),
        currency="EUR",
    )
    svc = InvoiceService()
    svc.mark_invoice_paid_by_staff(invoice=invoice, actor=user, source="test")
    invoice.refresh_from_db()
    with pytest.raises(ValidationError):
        svc.mark_invoice_paid_by_staff(invoice=invoice, actor=user, source="test")


@pytest.mark.django_db
def test_ensure_invoice_sets_paid_at_for_captured_paypal():
    user = get_user_model().objects.create_user(email="pp@example.com", password="pass")
    customer = Customer.objects.create(name="PayPalCo", preferred_settlement_method="paypal")
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        currency="EUR",
        subtotal_amount=Decimal("50.00"),
        total_amount=Decimal("50.00"),
    )
    payment = Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.CAPTURED,
        amount=Decimal("50.00"),
        currency="EUR",
        paypal_capture_id="cap-test",
    )
    svc = InvoiceService()
    inv = svc.ensure_invoice_for_captured_payment(order=order, payment=payment, source="test")
    assert inv.paid_at is not None
    assert inv.issued_at is not None
