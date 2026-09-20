import hashlib
import hmac
import json
import time
from datetime import timedelta

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.billing import views as billing_views
from apps.billing.models import Payment
from apps.billing.services.gateways import PaymentGatewayTransientError
from apps.billing.services.payments import PaymentService
from apps.billing.services.paypal import PayPalAPIError, PayPalBindingError, PayPalGateway
from apps.billing.services.stripe_gateway import StripeAPIError, StripeGateway, StripeTransientError
from apps.billing.tasks import recover_incomplete_captures_task
from apps.notifications.models import WorkshopNotificationEvent
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from tests.billing.test_billing_api import (
    FakePayPalGateway,
    FakeStripeGateway,
    create_customer_scope,
    create_order,
)


def _initiate(service, *, customer, order, user, provider):
    return service.initiate_payment_for_customer_order(
        customer=customer,
        order_public_id=order.public_id,
        actor=user,
        source="test",
        provider=provider,
        success_url="https://example.com/success",
        cancel_url="https://example.com/cancel",
    )


def _stripe_signature(body: bytes) -> str:
    timestamp = int(time.time())
    digest = hmac.new(b"whsec_test", f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


@pytest.mark.django_db
@override_settings(PAYPAL_CLIENT_ID="paypal-id", PAYPAL_CLIENT_SECRET="paypal-secret")
def test_checkout_cannot_switch_provider_while_first_is_payable():
    user, customer = create_customer_scope(email="switch@example.com", customer_name="Switch")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakePayPalGateway())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )

    _, reused = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    assert reused.pk == payment.pk
    with pytest.raises(ValidationError, match="déjà ouvert"):
        _initiate(
            PaymentService(gateway=FakeStripeGateway()),
            customer=customer,
            order=order,
            user=user,
            provider=Payment.Provider.STRIPE,
        )
    assert Payment.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_captured_order_cannot_open_new_checkout():
    user, customer = create_customer_scope(email="paid-once@example.com", customer_name="Paid")
    order = create_order(customer, user)
    Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id="cs_paid_once",
        stripe_payment_intent_id="pi_paid_once",
    )
    with pytest.raises(ValidationError, match="déjà réglée"):
        _initiate(
            PaymentService(gateway=FakeStripeGateway()),
            customer=customer,
            order=order,
            user=user,
            provider=Payment.Provider.STRIPE,
        )


@pytest.mark.django_db
def test_database_rejects_active_attempt_beside_captured_payment():
    user, customer = create_customer_scope(email="mixed@example.com", customer_name="Mixed")
    order = create_order(customer, user)
    Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount=order.total_amount,
        currency=order.currency,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Payment.objects.create(
            order=order,
            provider=Payment.Provider.PAYPAL,
            status=Payment.Status.PENDING,
            amount=order.total_amount,
            currency=order.currency,
        )


@pytest.mark.django_db
def test_capture_rejects_price_changed_after_checkout():
    user, customer = create_customer_scope(email="price-race@example.com", customer_name="Price")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    order.total_amount = "30.00"
    order.save(update_fields=("total_amount", "updated_at"))

    with pytest.raises(ValidationError, match="montant de la commande"):
        service.confirm_stripe_checkout_session(
            checkout_session_id=payment.stripe_checkout_session_id,
            source="test",
        )
    payment.refresh_from_db()
    assert payment.status != Payment.Status.CAPTURED


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_early_stripe_webhook_recovers_payment_by_public_id(monkeypatch):
    user, customer = create_customer_scope(email="early@example.com", customer_name="Early")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    monkeypatch.setattr(
        billing_views, "payment_service", PaymentService(gateway=FakeStripeGateway())
    )
    body = json.dumps(
        {
            "id": "evt_early",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_early",
                    "payment_status": "paid",
                    "metadata": {"payment_public_id": str(payment.public_id)},
                }
            },
        }
    ).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(body),
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.stripe_checkout_session_id == "cs_early"
    assert payment.status == Payment.Status.CAPTURED


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_unmatched_stripe_webhook_requests_retry():
    body = json.dumps(
        {
            "id": "evt_unknown",
            "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_unknown", "payment_status": "paid"}},
        }
    ).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(body),
    )
    assert response.status_code == 503


@pytest.mark.django_db
def test_transient_stripe_lookup_preserves_payable_attempt():
    user, customer = create_customer_scope(email="transient@example.com", customer_name="Transient")
    order = create_order(customer, user)

    class TemporarilyUnavailable(FakeStripeGateway):
        def confirm_checkout(self, *, provider_payment_id):
            raise StripeTransientError("temporary")

    service = PaymentService(gateway=TemporarilyUnavailable())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    with pytest.raises(StripeTransientError):
        service.confirm_stripe_checkout_session(
            checkout_session_id=payment.stripe_checkout_session_id,
            source="test",
        )
    payment.refresh_from_db()
    assert payment.status in (Payment.Status.PENDING, Payment.Status.APPROVED)


@pytest.mark.django_db
def test_checkout_create_timeout_reuses_same_attempt_and_blocks_provider_switch():
    user, customer = create_customer_scope(email="timeout@example.com", customer_name="Timeout")
    order = create_order(customer, user)

    class LostResponse(FakeStripeGateway):
        def __init__(self):
            super().__init__()
            self.keys = []

        def create_checkout(self, *, order, success_url, cancel_url, idempotency_key=""):
            self.keys.append(idempotency_key)
            if len(self.keys) == 1:
                raise StripeTransientError("response lost")
            return super().create_checkout(
                order=order,
                success_url=success_url,
                cancel_url=cancel_url,
                idempotency_key=idempotency_key,
            )

    gateway = LostResponse()
    service = PaymentService(gateway=gateway)
    with pytest.raises(PaymentGatewayTransientError):
        _initiate(
            service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
        )
    pending = Payment.objects.get(order=order)
    assert pending.status == Payment.Status.PENDING
    with pytest.raises(ValidationError, match="déjà ouvert"):
        _initiate(
            PaymentService(gateway=FakePayPalGateway()),
            customer=customer,
            order=order,
            user=user,
            provider=Payment.Provider.PAYPAL,
        )
    _, retried = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    assert retried.pk == pending.pk
    assert gateway.keys == [str(pending.public_id), str(pending.public_id)]
    assert Payment.objects.filter(order=order).count() == 1


@pytest.mark.django_db
def test_unknown_checkout_is_not_recreated_after_idempotency_window():
    user, customer = create_customer_scope(email="aged@example.com", customer_name="Aged")
    order = create_order(customer, user)

    class MustNotCreate(FakeStripeGateway):
        def create_checkout(self, **kwargs):
            pytest.fail("Une nouvelle session distante ne doit pas être créée.")

    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=24))
    with pytest.raises(ValidationError, match="réponse du prestataire manque"):
        _initiate(
            PaymentService(gateway=MustNotCreate()),
            customer=customer,
            order=order,
            user=user,
            provider=Payment.Provider.STRIPE,
        )
    payment.refresh_from_db()
    assert payment.status == Payment.Status.PENDING


@pytest.mark.django_db
def test_known_remote_checkout_without_url_is_resumed_not_recreated():
    user, customer = create_customer_scope(email="resume@example.com", customer_name="Resume")
    order = create_order(customer, user)

    class ResumableStripe(FakeStripeGateway):
        def checkout_state(self, *, provider_payment_id):
            return "OPEN"

        def create_checkout(self, **kwargs):
            pytest.fail("La création ne doit pas être répétée avec un ID connu.")

        def resume_checkout(self, *, provider_payment_id, order, payment_public_id):
            return type(
                "CheckoutCreateResult",
                (),
                {
                    "provider_payment_id": provider_payment_id,
                    "status": "OPEN",
                    "checkout_url": "https://checkout.stripe.com/c/pay/resumed",
                    "payload": {"id": provider_payment_id},
                    "provider_capture_id": "",
                },
            )()

    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id="cs_known_resume",
    )
    _, resumed = _initiate(
        PaymentService(gateway=ResumableStripe()),
        customer=customer,
        order=order,
        user=user,
        provider=Payment.Provider.STRIPE,
    )
    assert resumed.pk == payment.pk
    assert resumed.approval_url.endswith("/resumed")
    assert Payment.objects.filter(order=order).count() == 1


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_stripe_resume_rejects_session_for_another_payment(monkeypatch):
    user, customer = create_customer_scope(email="stripe-resume@example.com", customer_name="SR")
    order = create_order(customer, user)
    gateway = StripeGateway()
    monkeypatch.setattr(
        gateway,
        "_request_form",
        lambda **_kwargs: {
            "id": "cs_foreign",
            "status": "open",
            "payment_status": "unpaid",
            "client_reference_id": str(order.public_id),
            "metadata": {"payment_public_id": "another-payment"},
            "amount_total": 2500,
            "currency": "eur",
            "url": "https://checkout.stripe.com/c/pay/foreign",
        },
    )
    with pytest.raises(StripeAPIError, match="impossible à reprendre"):
        gateway.resume_checkout(
            provider_payment_id="cs_foreign",
            order=order,
            payment_public_id="expected-payment",
        )


@pytest.mark.django_db
@override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
def test_paypal_resume_rejects_order_for_another_payment(monkeypatch):
    user, customer = create_customer_scope(email="paypal-resume@example.com", customer_name="PR")
    order = create_order(customer, user)
    gateway = PayPalGateway()
    monkeypatch.setattr(
        gateway,
        "get_order",
        lambda **_kwargs: {
            "id": "PP-FOREIGN",
            "status": "CREATED",
            "purchase_units": [
                {
                    "custom_id": "another-payment",
                    "reference_id": order.public_id.hex,
                    "amount": {"value": "25.00", "currency_code": "EUR"},
                }
            ],
            "links": [{"rel": "approve", "href": "https://www.paypal.com/checkoutnow"}],
        },
    )
    with pytest.raises(PayPalAPIError, match="impossible à reprendre"):
        gateway.resume_checkout(
            provider_payment_id="PP-FOREIGN",
            order=order,
            payment_public_id="expected-payment",
        )


@pytest.mark.django_db
def test_pdf_failure_keeps_confirmed_capture_and_retry_finishes_release():
    user, customer = create_customer_scope(email="pdf-fail@example.com", customer_name="PDF fail")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    original = service.invoice_service.ensure_invoice_for_captured_payment
    attempts = 0

    def fail_once(**kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("storage down")
        return original(**kwargs)

    service.invoice_service.ensure_invoice_for_captured_payment = fail_once
    with pytest.raises(OSError, match="storage down"):
        service.confirm_stripe_checkout_session(
            checkout_session_id=payment.stripe_checkout_session_id, source="test"
        )
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    _, _, invoice = service.confirm_stripe_checkout_session(
        checkout_session_id=payment.stripe_checkout_session_id, source="test_retry"
    )
    assert invoice is not None
    assert invoice.file


@pytest.mark.django_db
def test_periodic_recovery_releases_paid_order_after_pdf_storage_failure():
    user, customer = create_customer_scope(email="recover@example.com", customer_name="Recover")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )

    def storage_down(**kwargs):
        raise OSError("storage unavailable")

    service.invoice_service.ensure_invoice_for_captured_payment = storage_down
    with pytest.raises(OSError, match="storage unavailable"):
        service.confirm_stripe_checkout_session(
            checkout_session_id=payment.stripe_checkout_session_id, source="test"
        )
    payment.refresh_from_db()
    Payment.objects.filter(pk=payment.pk).update(captured_at=timezone.now() - timedelta(minutes=3))
    assert payment.status == Payment.Status.CAPTURED
    assert not WorkshopNotificationEvent.objects.filter(order=order).exists()

    result = recover_incomplete_captures_task()
    assert result == {"recovered": 1, "failed": 0}
    assert order.invoice.file
    assert WorkshopNotificationEvent.objects.filter(
        order=order,
        event_type=WorkshopNotificationEvent.EventType.ORDER_SUBMITTED,
    ).exists()
    assert recover_incomplete_captures_task() == {"recovered": 0, "failed": 0}


@pytest.mark.django_db
def test_periodic_recovery_restores_missing_receipt_file():
    user, customer = create_customer_scope(email="receipt@example.com", customer_name="Receipt")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakeStripeGateway())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    _, _, invoice = service.confirm_stripe_checkout_session(
        checkout_session_id=payment.stripe_checkout_session_id, source="test"
    )
    invoice.file.delete(save=True)
    Payment.objects.filter(pk=payment.pk).update(captured_at=timezone.now() - timedelta(minutes=3))
    assert recover_incomplete_captures_task() == {"recovered": 1, "failed": 0}
    invoice.refresh_from_db()
    assert invoice.file


@pytest.mark.django_db
def test_periodic_reconciliation_recovers_remote_stripe_capture_without_webhook():
    user, customer = create_customer_scope(email="remote-paid@example.com", customer_name="Remote")
    order = create_order(customer, user)

    class RemotelyPaidStripe(FakeStripeGateway):
        def checkout_state(self, *, provider_payment_id):
            return "COMPLETED"

    service = PaymentService(gateway=RemotelyPaidStripe())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now() - timedelta(minutes=3))
    assert service.reconcile_active_payments() == {"reconciled": 1, "failed": 0}
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert order.invoice.file
    assert WorkshopNotificationEvent.objects.filter(order=order).exists()


@pytest.mark.django_db
def test_periodic_reconciliation_captures_approved_paypal_without_return_or_webhook():
    user, customer = create_customer_scope(email="paypal-approved@example.com", customer_name="AP")
    order = create_order(customer, user)

    class RemotelyApprovedPayPal(FakePayPalGateway):
        def checkout_state(self, *, provider_payment_id):
            return "APPROVED"

    service = PaymentService(gateway=RemotelyApprovedPayPal())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    assert payment.approval_url
    Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now() - timedelta(minutes=3))
    assert service.reconcile_active_payments() == {"reconciled": 1, "failed": 0}
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CAPTURED
    assert order.invoice.file
    assert WorkshopNotificationEvent.objects.filter(order=order).exists()


@pytest.mark.django_db
@override_settings(PAYPAL_API_BASE_URL="https://api-m.paypal.com")
def test_initiate_discards_sandbox_approval_url_after_live_switch():
    user, customer = create_customer_scope(email="paypal-env@example.com", customer_name="Env")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakePayPalGateway())
    _, stale = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    Payment.objects.filter(pk=stale.pk).update(
        approval_url="https://www.sandbox.paypal.com/checkoutnow?token=SANDBOXTOKEN",
        paypal_order_id="SANDBOXTOKEN",
    )
    _, fresh = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    stale.refresh_from_db()
    assert stale.status == Payment.Status.CANCELLED
    assert fresh.pk != stale.pk
    assert fresh.status in {Payment.Status.PENDING, Payment.Status.APPROVED}
    assert "sandbox.paypal.com" not in (fresh.approval_url or "")
    assert fresh.approval_url


@pytest.mark.django_db
def test_initiate_creates_new_paypal_checkout_when_remote_order_is_gone():
    user, customer = create_customer_scope(email="paypal-gone@example.com", customer_name="Gone")
    order = create_order(customer, user)

    class MissingRemotePayPal(FakePayPalGateway):
        def checkout_state(self, *, provider_payment_id):
            raise PayPalAPIError("RESOURCE_NOT_FOUND INVALID_RESOURCE_ID")

    service = PaymentService(gateway=MissingRemotePayPal())
    _, stale = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    Payment.objects.filter(pk=stale.pk).update(
        paypal_order_id="PP-GONE",
        approval_url="https://www.paypal.com/checkoutnow?token=PP-GONE",
    )
    _, fresh = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    stale.refresh_from_db()
    assert stale.status == Payment.Status.CANCELLED
    assert fresh.pk != stale.pk
    assert fresh.approval_url
    assert fresh.provider_payment_id != "PP-GONE"


@pytest.mark.django_db
def test_cancel_open_checkouts_for_order_closes_pending_paypal():
    user, customer = create_customer_scope(email="paypal-cancel@example.com", customer_name="CX")
    order = create_order(customer, user)
    service = PaymentService(gateway=FakePayPalGateway())
    _, payment = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    assert payment.status in {Payment.Status.PENDING, Payment.Status.APPROVED}
    closed = service.cancel_open_checkouts_for_order(
        order=order, actor=user, source="test_cancel"
    )
    payment.refresh_from_db()
    assert closed == 1
    assert payment.status == Payment.Status.CANCELLED
    _, fresh = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.PAYPAL
    )
    assert fresh.pk != payment.pk
    assert fresh.approval_url


@pytest.mark.django_db
def test_reconciliation_failure_rotates_past_batch_limit():
    user_a, customer_a = create_customer_scope(email="rotate-a@example.com", customer_name="RA")
    user_b, customer_b = create_customer_scope(email="rotate-b@example.com", customer_name="RB")
    order_a = create_order(customer_a, user_a)
    order_b = create_order(customer_b, user_b)

    class FirstSessionUnavailable(FakeStripeGateway):
        def checkout_state(self, *, provider_payment_id):
            if provider_payment_id == first.stripe_checkout_session_id:
                raise PaymentGatewayTransientError("Stripe temporarily unavailable")
            return "COMPLETED"

    service = PaymentService(gateway=FirstSessionUnavailable())
    _, first = _initiate(
        service, customer=customer_a, order=order_a, user=user_a, provider=Payment.Provider.STRIPE
    )
    _, second = _initiate(
        service, customer=customer_b, order=order_b, user=user_b, provider=Payment.Provider.STRIPE
    )
    Payment.objects.filter(pk=first.pk).update(updated_at=timezone.now() - timedelta(minutes=4))
    Payment.objects.filter(pk=second.pk).update(updated_at=timezone.now() - timedelta(minutes=3))
    assert service.reconcile_active_payments(limit=1) == {"reconciled": 0, "failed": 1}
    assert service.reconcile_active_payments(limit=1) == {"reconciled": 1, "failed": 0}
    second.refresh_from_db()
    assert second.status == Payment.Status.CAPTURED


@pytest.mark.django_db
def test_capture_recovery_failure_rotates_past_batch_limit():
    user_a, customer_a = create_customer_scope(email="recover-a@example.com", customer_name="RCA")
    user_b, customer_b = create_customer_scope(email="recover-b@example.com", customer_name="RCB")
    order_a = create_order(customer_a, user_a)
    order_b = create_order(customer_b, user_b)
    first = Payment.objects.create(
        order=order_a,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount=order_a.total_amount,
        currency=order_a.currency,
        stripe_checkout_session_id="cs_recover_first",
        stripe_payment_intent_id="pi_recover_first",
        captured_at=timezone.now() - timedelta(minutes=5),
    )
    second = Payment.objects.create(
        order=order_b,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount=order_b.total_amount,
        currency=order_b.currency,
        stripe_checkout_session_id="cs_recover_second",
        stripe_payment_intent_id="pi_recover_second",
        captured_at=timezone.now() - timedelta(minutes=4),
    )
    Payment.objects.filter(pk=first.pk).update(updated_at=timezone.now() - timedelta(minutes=4))
    Payment.objects.filter(pk=second.pk).update(updated_at=timezone.now() - timedelta(minutes=3))
    service = PaymentService()
    original = service.invoice_service.ensure_invoice_for_captured_payment

    def fail_first(*, order, **kwargs):
        if order.pk == order_a.pk:
            raise OSError("first invoice storage unavailable")
        return original(order=order, **kwargs)

    service.invoice_service.ensure_invoice_for_captured_payment = fail_first
    assert service.recover_incomplete_captures(limit=1) == {"recovered": 0, "failed": 1}
    assert service.recover_incomplete_captures(limit=1) == {"recovered": 1, "failed": 0}
    assert order_b.invoice.file


@pytest.mark.django_db
def test_manual_unknown_checkout_closure_requires_permission_evidence_and_age():
    user, customer = create_customer_scope(email="unknown-close@example.com", customer_name="Close")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    user.is_staff = True
    user.save(update_fields=("is_staff",))
    options = dict(
        resolution="no_remote_checkout",
        evidence="Stripe dashboard search 12345",
        reason="No remote checkout was created",
    )
    with pytest.raises(ValidationError, match="Permission"):
        PaymentService().close_unknown_checkout_after_reconciliation(
            payment_public_id=payment.public_id,
            actor=user,
            **options,
        )
    with pytest.raises(CommandError, match="fenêtre"):
        call_command("resolve_unknown_payment", str(payment.public_id), **options)
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=24))
    call_command("resolve_unknown_payment", str(payment.public_id), **options)
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CANCELLED
    assert Payment.objects.filter(order=order, status=Payment.Status.CAPTURED).count() == 0


@pytest.mark.django_db
def test_manual_unknown_checkout_closure_rejects_known_remote_reference():
    user, customer = create_customer_scope(email="known-close@example.com", customer_name="Known")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id="cs_known_ref",
    )
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(hours=24))
    user.is_staff = True
    user.save(update_fields=("is_staff",))
    with pytest.raises(CommandError, match="référence prestataire"):
        call_command(
            "resolve_unknown_payment",
            str(payment.public_id),
            resolution="remote_closed",
            evidence="Stripe dashboard search 12345",
            reason="Provider checkout was closed",
        )


@pytest.mark.django_db
def test_historical_failed_checkout_without_reference_can_be_audited():
    user, customer = create_customer_scope(email="old-failed@example.com", customer_name="Old")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.FAILED,
        amount=order.total_amount,
        currency=order.currency,
    )
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - timedelta(days=2))
    options = {
        "resolution": "no_remote_checkout",
        "evidence": "Stripe dashboard search for payment public id found no checkout",
        "reason": "Historical lost response reconciled before payment cutover",
    }
    call_command("resolve_unknown_payment", str(payment.public_id), **options)
    payment.refresh_from_db()
    assert payment.status == Payment.Status.CANCELLED
    assert AuditLogEntry.objects.filter(
        action="billing.unknown_checkout_manually_closed",
        target_public_id=payment.public_id,
    ).exists()
    with pytest.raises(CommandError, match="déjà été rapprochée"):
        call_command("resolve_unknown_payment", str(payment.public_id), **options)


@pytest.mark.django_db
def test_expired_stripe_checkout_can_be_replaced_without_second_payable_session():
    user, customer = create_customer_scope(email="expired@example.com", customer_name="Expired")
    order = create_order(customer, user)

    class ExpiringStripe(FakeStripeGateway):
        def checkout_state(self, *, provider_payment_id):
            return "EXPIRED"

    service = PaymentService(gateway=ExpiringStripe())
    _, first = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    _, second = _initiate(
        service, customer=customer, order=order, user=user, provider=Payment.Provider.STRIPE
    )
    first.refresh_from_db()
    assert first.status == Payment.Status.CANCELLED
    assert second.pk != first.pk
    assert Payment.objects.filter(order=order, status=Payment.Status.APPROVED).count() == 1


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_early_stripe_failure_event_binds_attempt_without_releasing_checkout(monkeypatch):
    user, customer = create_customer_scope(email="early-fail@example.com", customer_name="Fail")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    monkeypatch.setattr(
        billing_views,
        "payment_service",
        PaymentService(gateway=FakeStripeGateway(pending_confirm=True)),
    )
    body = json.dumps(
        {
            "id": "evt_early_failed",
            "type": "checkout.session.async_payment_failed",
            "data": {
                "object": {
                    "id": "cs_early_failed",
                    "metadata": {"payment_public_id": str(payment.public_id)},
                }
            },
        }
    ).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(body),
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.stripe_checkout_session_id == "cs_early_failed"
    assert payment.status == Payment.Status.PENDING


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_saved_legacy_stripe_session_without_payment_metadata_can_capture(monkeypatch):
    user, customer = create_customer_scope(email="legacy-paid@example.com", customer_name="Legacy")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
        stripe_checkout_session_id="cs_legacy_paid",
    )
    gateway = StripeGateway()
    monkeypatch.setattr(
        gateway,
        "_request_form",
        lambda **_kwargs: {
            "id": "cs_legacy_paid",
            "client_reference_id": str(order.public_id),
            "metadata": {
                "order_public_id": str(order.public_id),
                "customer_public_id": str(customer.public_id),
            },
            "amount_total": 2500,
            "currency": "eur",
            "payment_status": "paid",
            "status": "complete",
            "payment_intent": "pi_legacy_paid",
        },
    )
    _, captured, invoice = PaymentService(gateway=gateway).confirm_stripe_checkout_session(
        checkout_session_id="cs_legacy_paid",
        source="legacy_reconciliation",
    )
    assert captured.pk == payment.pk
    assert captured.status == Payment.Status.CAPTURED
    assert invoice is not None


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_unstored_stripe_session_cannot_bind_legacy_missing_payment_metadata(monkeypatch):
    user, customer = create_customer_scope(email="legacy-early@example.com", customer_name="Legacy")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    gateway = StripeGateway()
    monkeypatch.setattr(
        gateway,
        "_request_form",
        lambda **_kwargs: {
            "id": "cs_legacy_unstored",
            "client_reference_id": str(order.public_id),
            "metadata": {
                "order_public_id": str(order.public_id),
                "customer_public_id": str(customer.public_id),
            },
            "amount_total": 2500,
            "currency": "eur",
        },
    )
    with pytest.raises(ValidationError, match="autre tentative"):
        PaymentService(gateway=gateway).confirm_stripe_checkout_session(
            checkout_session_id="cs_legacy_unstored",
            payment_public_id=str(payment.public_id),
            source="early_legacy_webhook",
        )
    payment.refresh_from_db()
    assert payment.stripe_checkout_session_id == ""
    assert payment.status == Payment.Status.PENDING


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy")
def test_saved_legacy_stripe_checkout_url_can_resume_with_customer_binding(monkeypatch):
    user, customer = create_customer_scope(
        email="legacy-resume@example.com", customer_name="Legacy"
    )
    order = create_order(customer, user)
    gateway = StripeGateway()
    payload = {
        "id": "cs_legacy_resume",
        "status": "open",
        "payment_status": "unpaid",
        "client_reference_id": str(order.public_id),
        "metadata": {
            "order_public_id": str(order.public_id),
            "customer_public_id": str(customer.public_id),
        },
        "amount_total": 2500,
        "currency": "eur",
        "url": "https://checkout.stripe.com/c/pay/cs_legacy_resume",
    }
    monkeypatch.setattr(gateway, "_request_form", lambda **_kwargs: payload)
    resumed = gateway.resume_checkout(
        provider_payment_id="cs_legacy_resume",
        order=order,
        payment_public_id="legacy-payment-id",
    )
    assert resumed.checkout_url == payload["url"]
    payload["metadata"]["customer_public_id"] = "another-customer"
    with pytest.raises(StripeAPIError, match="rapprochement"):
        gateway.resume_checkout(
            provider_payment_id="cs_legacy_resume",
            order=order,
            payment_public_id="legacy-payment-id",
        )


@pytest.mark.django_db
def test_early_paypal_confirmation_binds_public_attempt_id():
    user, customer = create_customer_scope(email="early-paypal@example.com", customer_name="PayPal")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    service = PaymentService(gateway=FakePayPalGateway())
    _, confirmed, invoice = service.confirm_capture(
        order_public_id="",
        paypal_order_id="PP-EARLY-ORDER",
        payment_public_id=str(payment.public_id),
        source="test_early_webhook",
    )
    assert confirmed.pk == payment.pk
    assert confirmed.paypal_order_id == "PP-EARLY-ORDER"
    assert confirmed.status == Payment.Status.CAPTURED
    assert invoice is not None


@pytest.mark.django_db
def test_paypal_early_token_cannot_be_bound_to_another_order_or_customer():
    user_a, customer_a = create_customer_scope(email="bind-a@example.com", customer_name="Bind A")
    user_b, customer_b = create_customer_scope(email="bind-b@example.com", customer_name="Bind B")
    order_a = create_order(customer_a, user_a)
    order_b = create_order(customer_b, user_b)
    payment_b = Payment.objects.create(
        order=order_b,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.PENDING,
        amount=order_b.total_amount,
        currency=order_b.currency,
    )
    _order, payment, _invoice = PaymentService(gateway=FakePayPalGateway()).confirm_capture(
        order_public_id=order_a.public_id,
        paypal_order_id="PP-FOREIGN-TOKEN",
        payment_public_id=payment_b.public_id,
        source="browser_return",
    )
    assert payment is None
    payment_b.refresh_from_db()
    assert payment_b.paypal_order_id == ""
    assert payment_b.status == Payment.Status.PENDING


@override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
def test_paypal_gateway_rejects_foreign_order_reference_before_capture(monkeypatch):
    gateway = PayPalGateway()
    monkeypatch.setattr(
        gateway,
        "get_order",
        lambda **_kwargs: {
            "id": "PP-ORDER",
            "purchase_units": [{"custom_id": "payment-a", "reference_id": "another-order"}],
        },
    )
    with pytest.raises(PayPalAPIError, match="autre tentative"):
        gateway.verify_checkout_binding(
            provider_payment_id="PP-ORDER",
            payment_public_id="payment-a",
            order_public_id="8762c14a-0011-44a2-9ff0-fb459490c923",
        )


@override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
def test_paypal_rejects_amount_mismatch_before_remote_capture(monkeypatch):
    gateway = PayPalGateway()
    monkeypatch.setattr(
        gateway,
        "get_order",
        lambda **_kwargs: {
            "id": "PP-ORDER",
            "purchase_units": [
                {
                    "custom_id": "payment-a",
                    "reference_id": "8762c14a001144a29ff0fb459490c923",
                    "amount": {"value": "26.00", "currency_code": "EUR"},
                }
            ],
        },
    )
    with pytest.raises(PayPalBindingError, match="Montant ou devise"):
        gateway.verify_checkout_binding(
            provider_payment_id="PP-ORDER",
            payment_public_id="payment-a",
            order_public_id="8762c14a-0011-44a2-9ff0-fb459490c923",
            amount="25.00",
            currency="EUR",
        )


@pytest.mark.django_db
@override_settings(PAYPAL_CLIENT_ID="client", PAYPAL_CLIENT_SECRET="secret")
def test_paypal_amount_mismatch_never_calls_capture_endpoint(monkeypatch):
    user, customer = create_customer_scope(email="paypal-amount@example.com", customer_name="PA")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.APPROVED,
        amount=order.total_amount,
        currency=order.currency,
        paypal_order_id="PP-AMOUNT",
    )
    gateway = PayPalGateway()
    monkeypatch.setattr(
        gateway,
        "get_order",
        lambda **_kwargs: {
            "id": "PP-AMOUNT",
            "purchase_units": [
                {
                    "custom_id": str(payment.public_id),
                    "reference_id": order.public_id.hex,
                    "amount": {"value": "26.00", "currency_code": "EUR"},
                }
            ],
        },
    )
    capture_called = []
    monkeypatch.setattr(
        gateway,
        "capture_order",
        lambda **_kwargs: capture_called.append(True),
    )
    with pytest.raises(ValidationError, match="Montant ou devise"):
        PaymentService(gateway=gateway).confirm_capture(
            order_public_id=order.public_id,
            provider_payment_id="PP-AMOUNT",
            source="test",
        )
    assert capture_called == []
    payment.refresh_from_db()
    assert payment.status == Payment.Status.APPROVED


@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_stripe_rejects_foreign_customer_before_binding(monkeypatch):
    gateway = StripeGateway()
    monkeypatch.setattr(
        gateway,
        "_request_form",
        lambda **_kwargs: {
            "id": "cs_foreign_customer",
            "client_reference_id": "order-a",
            "metadata": {
                "order_public_id": "order-a",
                "customer_public_id": "customer-b",
                "payment_public_id": "payment-a",
            },
            "amount_total": 2500,
            "currency": "eur",
        },
    )
    with pytest.raises(StripeAPIError, match="autre tentative"):
        gateway.verify_checkout_binding(
            provider_payment_id="cs_foreign_customer",
            payment_public_id="payment-a",
            order_public_id="order-a",
            customer_public_id="customer-a",
            amount="25.00",
            currency="EUR",
        )


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_signed_foreign_stripe_webhook_cannot_bind_cross_customer(monkeypatch):
    user_a, customer_a = create_customer_scope(email="stripe-a@example.com", customer_name="SA")
    user_b, customer_b = create_customer_scope(email="stripe-b@example.com", customer_name="SB")
    order_a = create_order(customer_a, user_a)
    order_b = create_order(customer_b, user_b)
    payment_a = Payment.objects.create(
        order=order_a,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order_a.total_amount,
        currency=order_a.currency,
    )
    gateway = StripeGateway()
    monkeypatch.setattr(
        gateway,
        "_request_form",
        lambda **_kwargs: {
            "id": "cs_cross_customer",
            "client_reference_id": str(order_b.public_id),
            "metadata": {
                "order_public_id": str(order_b.public_id),
                "customer_public_id": str(customer_b.public_id),
                "payment_public_id": str(payment_a.public_id),
            },
            "amount_total": 2500,
            "currency": "eur",
            "payment_status": "paid",
            "payment_intent": "pi_foreign",
        },
    )
    monkeypatch.setattr(billing_views, "payment_service", PaymentService(gateway=gateway))
    body = json.dumps(
        {
            "id": "evt_cross_customer",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_cross_customer",
                    "payment_status": "paid",
                    "metadata": {"payment_public_id": str(payment_a.public_id)},
                }
            },
        }
    ).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(body),
    )
    assert response.status_code == 400
    payment_a.refresh_from_db()
    assert payment_a.stripe_checkout_session_id == ""
    assert payment_a.status == Payment.Status.PENDING


@pytest.mark.django_db
@override_settings(STRIPE_SECRET_KEY="sk_test_dummy", STRIPE_WEBHOOK_SECRET="whsec_test")
def test_signed_foreign_stripe_failure_cannot_cancel_other_customer(monkeypatch):
    user_a, customer_a = create_customer_scope(email="fail-a@example.com", customer_name="FA")
    user_b, customer_b = create_customer_scope(email="fail-b@example.com", customer_name="FB")
    order_a = create_order(customer_a, user_a)
    order_b = create_order(customer_b, user_b)
    payment_a = Payment.objects.create(
        order=order_a,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.PENDING,
        amount=order_a.total_amount,
        currency=order_a.currency,
    )
    gateway = StripeGateway()
    monkeypatch.setattr(
        gateway,
        "_request_form",
        lambda **_kwargs: {
            "id": "cs_foreign_failure",
            "client_reference_id": str(order_b.public_id),
            "metadata": {
                "order_public_id": str(order_b.public_id),
                "customer_public_id": str(customer_b.public_id),
                "payment_public_id": str(payment_a.public_id),
            },
            "amount_total": 2500,
            "currency": "eur",
        },
    )
    monkeypatch.setattr(billing_views, "payment_service", PaymentService(gateway=gateway))
    body = json.dumps(
        {
            "id": "evt_foreign_failure",
            "type": "checkout.session.async_payment_failed",
            "data": {
                "object": {
                    "id": "cs_foreign_failure",
                    "metadata": {"payment_public_id": str(payment_a.public_id)},
                }
            },
        }
    ).encode()
    response = APIClient().post(
        reverse("billing:backend-stripe-webhook"),
        data=body,
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE=_stripe_signature(body),
    )
    assert response.status_code == 400
    payment_a.refresh_from_db()
    assert payment_a.stripe_checkout_session_id == ""
    assert payment_a.status == Payment.Status.PENDING


@pytest.mark.django_db
def test_paypal_binding_mismatch_stops_capture_and_leaves_attempt_unbound():
    user, customer = create_customer_scope(email="mismatch@example.com", customer_name="Mismatch")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )

    class ForeignOrderGateway(FakePayPalGateway):
        def verify_checkout_binding(self, **_kwargs):
            raise PayPalBindingError("Commande PayPal liée à une autre tentative de paiement.")

        def confirm_checkout(self, **_kwargs):
            pytest.fail("La capture PayPal ne doit pas être appelée.")

    with pytest.raises(ValidationError, match="autre tentative"):
        PaymentService(gateway=ForeignOrderGateway()).confirm_capture(
            order_public_id=order.public_id,
            paypal_order_id="PP-FOREIGN",
            payment_public_id=payment.public_id,
            source="browser_return",
        )
    payment.refresh_from_db()
    assert payment.paypal_order_id == ""
    assert payment.status == Payment.Status.PENDING


@pytest.mark.django_db
@override_settings(
    PAYPAL_CLIENT_ID="paypal-id", PAYPAL_CLIENT_SECRET="paypal-secret", PAYPAL_WEBHOOK_ID="wh-test"
)
def test_early_paypal_capture_webhook_recovers_custom_id_from_remote_order(monkeypatch):
    user, customer = create_customer_scope(email="early-cap@example.com", customer_name="Cap")
    order = create_order(customer, user)
    payment = Payment.objects.create(
        order=order,
        provider=Payment.Provider.PAYPAL,
        status=Payment.Status.PENDING,
        amount=order.total_amount,
        currency=order.currency,
    )
    monkeypatch.setattr(
        billing_views, "payment_service", PaymentService(gateway=FakePayPalGateway())
    )
    monkeypatch.setattr(
        PayPalGateway,
        "verify_and_parse_webhook",
        lambda self, *, payload, headers: json.loads(payload.decode()),
    )
    monkeypatch.setattr(
        PayPalGateway,
        "get_order",
        lambda self, *, paypal_order_id: {
            "id": paypal_order_id,
            "purchase_units": [{"custom_id": str(payment.public_id)}],
        },
    )
    event = {
        "id": "WH-EARLY-CAP",
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": "CAP-EARLY",
            "supplementary_data": {"related_ids": {"order_id": "PP-EARLY-CAP"}},
        },
    }
    response = APIClient().post(
        reverse("billing:backend-paypal-webhook"),
        data=json.dumps(event).encode(),
        content_type="application/json",
    )
    assert response.status_code == 200
    payment.refresh_from_db()
    assert payment.paypal_order_id == "PP-EARLY-CAP"
    assert payment.status == Payment.Status.CAPTURED
