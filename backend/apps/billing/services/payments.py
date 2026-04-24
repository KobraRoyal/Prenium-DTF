from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.billing.models import Invoice, Payment
from apps.billing.services.invoices import InvoiceService
from apps.billing.services.paypal import (
    PayPalAPIError,
    PayPalConfigurationError,
    PayPalGateway,
)
from apps.orders.models import Order


class PaymentService:
    def __init__(
        self,
        *,
        gateway: PayPalGateway | None = None,
        invoice_service: InvoiceService | None = None,
    ):
        self.gateway = gateway
        self.invoice_service = invoice_service or InvoiceService()

    def initiate_payment_for_customer_order(
        self,
        *,
        customer,
        order_public_id,
        actor,
        source: str,
    ):
        order = self._get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            return None, None
        if order.billing_mode == Order.BillingMode.DEFERRED:
            raise ValidationError(
                "Les commandes en facturation différée ne sont pas payées en ligne."
            )
        if order.total_amount <= 0:
            raise ValidationError("Montant de commande invalide pour un paiement.")
        gateway = self._get_gateway()
        payment = Payment.objects.create(
            order=order,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
            provider=Payment.Provider.PAYPAL,
            status=Payment.Status.PENDING,
            amount=order.total_amount,
            currency=order.currency,
            source=source,
            request_snapshot={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "amount": f"{order.total_amount:.2f}",
                "currency": order.currency,
            },
        )
        try:
            result = gateway.create_order(order=order)
        except (PayPalAPIError, PayPalConfigurationError) as exc:
            self._mark_failed(payment=payment, actor=actor, source=source, message=str(exc))

        payment.status = (
            Payment.Status.APPROVED
            if str(result.status).upper() == "APPROVED"
            else Payment.Status.PENDING
        )
        payment.paypal_order_id = result.paypal_order_id
        payment.approval_url = result.approval_url
        payment.provider_payload = result.payload
        payment.last_error_message = ""
        payment.save(
            update_fields=[
                "status",
                "paypal_order_id",
                "approval_url",
                "provider_payload",
                "last_error_message",
                "updated_at",
            ]
        )
        record_event(
            action="billing.payment_initiated",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "payment_public_id": str(payment.public_id),
                "paypal_order_id": payment.paypal_order_id,
                "source": source,
            },
        )
        return order, payment

    def confirm_capture(
        self,
        *,
        order_public_id,
        paypal_order_id: str,
        payment_public_id=None,
        actor=None,
        source: str,
    ):
        payment = self._resolve_payment(
            order_public_id=order_public_id,
            paypal_order_id=paypal_order_id,
            payment_public_id=payment_public_id,
        )
        if payment is None:
            return None, None, None

        if payment.status == Payment.Status.CAPTURED and payment.paypal_capture_id:
            invoice = self.invoice_service.ensure_invoice_for_captured_payment(
                order=payment.order,
                payment=payment,
                source=source,
            )
            record_event(
                action="billing.payment_capture_idempotent",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=payment,
                metadata={
                    "order_public_id": str(payment.order.public_id),
                    "customer_public_id": str(payment.order.customer.public_id),
                    "payment_public_id": str(payment.public_id),
                    "source": source,
                },
            )
            return payment.order, payment, invoice

        gateway = self._get_gateway()
        try:
            result = gateway.capture_order(paypal_order_id=paypal_order_id)
        except (PayPalAPIError, PayPalConfigurationError) as exc:
            self._mark_failed(payment=payment, actor=actor, source=source, message=str(exc))

        capture_status = str(result.status).upper()
        if capture_status != "COMPLETED":
            self._mark_failed(
                payment=payment,
                actor=actor,
                source=source,
                message=f"PayPal capture status is '{result.status}'.",
            )

        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            if payment.status == Payment.Status.CAPTURED and payment.paypal_capture_id:
                invoice = self.invoice_service.ensure_invoice_for_captured_payment(
                    order=payment.order,
                    payment=payment,
                    source=source,
                )
                return payment.order, payment, invoice

            payment.status = Payment.Status.CAPTURED
            payment.paypal_capture_id = result.capture_id or payment.paypal_capture_id
            payment.provider_payload = result.payload
            payment.captured_at = timezone.now()
            payment.last_error_message = ""
            payment.save(
                update_fields=[
                    "status",
                    "paypal_capture_id",
                    "provider_payload",
                    "captured_at",
                    "last_error_message",
                    "updated_at",
                ]
            )

        invoice = self.invoice_service.ensure_invoice_for_captured_payment(
            order=payment.order,
            payment=payment,
            source=source,
        )
        record_event(
            action="billing.payment_captured",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            metadata={
                "order_public_id": str(payment.order.public_id),
                "customer_public_id": str(payment.order.customer.public_id),
                "payment_public_id": str(payment.public_id),
                "invoice_public_id": str(invoice.public_id),
                "paypal_capture_id": payment.paypal_capture_id,
                "source": source,
            },
        )
        from apps.notifications.services.transactional import schedule_payment_captured_email

        schedule_payment_captured_email(order_public_id=payment.order.public_id)
        return payment.order, payment, invoice

    def get_customer_invoice(self, *, customer, order_public_id):
        order = self._get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            return None, None
        invoice = (
            Invoice.objects.for_customer(customer)
            .filter(order=order)
            .select_related("payment")
            .first()
        )
        return order, invoice

    def get_customer_billing(self, *, customer, order_public_id):
        order = self._get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            return None, None, None
        payment = (
            Payment.objects.for_order(order)
            .select_related("order", "order__customer")
            .order_by("-created_at")
            .first()
        )
        invoice = (
            Invoice.objects.for_customer(customer)
            .filter(order=order)
            .select_related("payment")
            .first()
        )
        return order, payment, invoice

    def get_staff_billing(self, *, order_public_id, actor, source: str):
        order = (
            Order.objects.select_related("customer")
            .filter(public_id=order_public_id)
            .first()
        )
        if order is None:
            return None, None, None
        payment = (
            Payment.objects.for_order(order)
            .select_related("order", "order__customer")
            .order_by("-created_at")
            .first()
        )
        invoice = (
            Invoice.objects.filter(order=order)
            .select_related("payment", "paid_recorded_by")
            .first()
        )
        if payment is not None:
            record_event(
                action="billing.staff_billing_viewed",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=payment,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "payment_public_id": str(payment.public_id),
                    "source": source,
                },
            )
        return order, payment, invoice

    def _get_customer_order(self, *, customer, order_public_id):
        return (
            Order.objects.select_related("customer")
            .filter(customer=customer, public_id=order_public_id)
            .first()
        )

    def _resolve_payment(self, *, order_public_id, paypal_order_id: str, payment_public_id=None):
        queryset = Payment.objects.select_related("order", "order__customer").filter(
            order__public_id=order_public_id
        )
        if payment_public_id:
            queryset = queryset.filter(public_id=payment_public_id)
        if paypal_order_id:
            queryset = queryset.filter(paypal_order_id=paypal_order_id)
        return queryset.order_by("-created_at").first()

    def _get_gateway(self) -> PayPalGateway:
        if self.gateway is None:
            self.gateway = PayPalGateway()
        return self.gateway

    def _mark_failed(self, *, payment: Payment, actor, source: str, message: str):
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            payment.status = Payment.Status.FAILED
            payment.last_error_message = str(message).strip()[:255]
            payment.save(update_fields=["status", "last_error_message", "updated_at"])
        record_event(
            action="billing.payment_failed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            status=AuditLogEntry.Status.FAILURE,
            message=payment.last_error_message,
            metadata={
                "order_public_id": str(payment.order.public_id),
                "customer_public_id": str(payment.order.customer.public_id),
                "payment_public_id": str(payment.public_id),
                "source": source,
            },
        )
        raise ValidationError(payment.last_error_message)

