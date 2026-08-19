from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.billing.models import Invoice, Payment
from apps.billing.services.gateways import (
    PaymentGateway,
    PaymentGatewayError,
    get_payment_gateway,
    resolve_online_provider,
)
from apps.billing.services.invoices import InvoiceService
from apps.orders.models import Order


class PaymentService:
    def __init__(
        self,
        *,
        gateway: PaymentGateway | None = None,
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
        provider: str | None = None,
        success_url: str = "",
        cancel_url: str = "",
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

        # Abandonne les tentatives ouvertes pour permettre une reprise propre.
        Payment.objects.filter(
            order_id=order.pk,
            status__in={Payment.Status.PENDING, Payment.Status.APPROVED},
        ).update(status=Payment.Status.CANCELLED)

        injected_provider = getattr(self.gateway, "provider", None) if self.gateway else None
        if injected_provider and (not provider or provider == injected_provider):
            resolved_provider = injected_provider
        else:
            resolved_provider = resolve_online_provider(
                customer=customer,
                requested_provider=provider,
            )
        gateway = self._get_gateway(provider=resolved_provider)
        payment = Payment.objects.create(
            order=order,
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
            provider=resolved_provider,
            status=Payment.Status.PENDING,
            amount=order.total_amount,
            currency=order.currency,
            source=source,
            request_snapshot={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "amount": f"{order.total_amount:.2f}",
                "currency": order.currency,
                "provider": resolved_provider,
            },
        )
        try:
            result = gateway.create_checkout(
                order=order,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except PaymentGatewayError as exc:
            self._mark_failed(payment=payment, actor=actor, source=source, message=str(exc))

        payment.status = (
            Payment.Status.APPROVED
            if str(result.status).upper() in {"APPROVED", "COMPLETE", "OPEN"}
            else Payment.Status.PENDING
        )
        self._apply_provider_ids(
            payment=payment,
            provider_payment_id=result.provider_payment_id,
            provider_capture_id=result.provider_capture_id,
        )
        payment.approval_url = result.checkout_url
        payment.provider_payload = result.payload
        payment.last_error_message = ""
        payment.save(
            update_fields=[
                "status",
                "paypal_order_id",
                "paypal_capture_id",
                "stripe_checkout_session_id",
                "stripe_payment_intent_id",
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
                "provider": payment.provider,
                "provider_payment_id": payment.provider_payment_id,
                "paypal_order_id": payment.paypal_order_id,
                "stripe_checkout_session_id": payment.stripe_checkout_session_id,
                "source": source,
            },
        )
        return order, payment

    def confirm_capture(
        self,
        *,
        order_public_id,
        paypal_order_id: str = "",
        payment_public_id=None,
        provider_payment_id: str = "",
        actor=None,
        source: str,
    ):
        resolved_provider_payment_id = (provider_payment_id or paypal_order_id or "").strip()
        payment = self._resolve_payment(
            order_public_id=order_public_id,
            provider_payment_id=resolved_provider_payment_id,
            payment_public_id=payment_public_id,
        )
        if payment is None:
            return None, None, None

        if payment.status == Payment.Status.CAPTURED and payment.provider_capture_id:
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
                    "provider": payment.provider,
                    "source": source,
                },
            )
            return payment.order, payment, invoice

        gateway = self._get_gateway(provider=payment.provider)
        try:
            result = gateway.confirm_checkout(
                provider_payment_id=payment.provider_payment_id or resolved_provider_payment_id
            )
        except PaymentGatewayError as exc:
            self._mark_failed(payment=payment, actor=actor, source=source, message=str(exc))

        capture_status = str(result.status).upper()
        if capture_status != "COMPLETED":
            self._mark_failed(
                payment=payment,
                actor=actor,
                source=source,
                message=f"{payment.provider} capture status is '{result.status}'.",
            )

        return self._finalize_captured_payment(
            payment=payment,
            provider_capture_id=result.provider_capture_id,
            provider_payload=result.payload,
            actor=actor,
            source=source,
        )

    def confirm_stripe_checkout_session(
        self,
        *,
        checkout_session_id: str,
        payment_intent_id: str = "",
        actor=None,
        source: str,
        event_id: str = "",
        payload: dict | None = None,
    ):
        payment = (
            Payment.objects.select_related("order", "order__customer")
            .filter(
                provider=Payment.Provider.STRIPE,
                stripe_checkout_session_id=checkout_session_id,
            )
            .order_by("-created_at")
            .first()
        )
        if payment is None:
            return None, None, None

        if payment.status == Payment.Status.CAPTURED and payment.stripe_payment_intent_id:
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
                    "provider": payment.provider,
                    "stripe_event_id": event_id,
                    "source": source,
                },
            )
            return payment.order, payment, invoice

        return self._finalize_captured_payment(
            payment=payment,
            provider_capture_id=payment_intent_id or payment.stripe_payment_intent_id,
            provider_payload=payload or payment.provider_payload,
            actor=actor,
            source=source,
            extra_metadata={"stripe_event_id": event_id} if event_id else None,
        )

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
        order = Order.objects.select_related("customer").filter(public_id=order_public_id).first()
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

    def _finalize_captured_payment(
        self,
        *,
        payment: Payment,
        provider_capture_id: str,
        provider_payload: dict,
        actor,
        source: str,
        extra_metadata: dict | None = None,
    ):
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            if payment.status == Payment.Status.CAPTURED and payment.provider_capture_id:
                invoice = self.invoice_service.ensure_invoice_for_captured_payment(
                    order=payment.order,
                    payment=payment,
                    source=source,
                )
                return payment.order, payment, invoice

            payment.status = Payment.Status.CAPTURED
            self._apply_provider_ids(
                payment=payment,
                provider_payment_id=payment.provider_payment_id,
                provider_capture_id=provider_capture_id or payment.provider_capture_id,
            )
            payment.provider_payload = provider_payload
            payment.captured_at = timezone.now()
            payment.last_error_message = ""
            payment.save(
                update_fields=[
                    "status",
                    "paypal_capture_id",
                    "stripe_payment_intent_id",
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
        metadata = {
            "order_public_id": str(payment.order.public_id),
            "customer_public_id": str(payment.order.customer.public_id),
            "payment_public_id": str(payment.public_id),
            "invoice_public_id": str(invoice.public_id),
            "provider": payment.provider,
            "provider_capture_id": payment.provider_capture_id,
            "paypal_capture_id": payment.paypal_capture_id,
            "stripe_payment_intent_id": payment.stripe_payment_intent_id,
            "source": source,
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        record_event(
            action="billing.payment_captured",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            metadata=metadata,
        )
        from apps.billing.services.production_payment_gate import (
            should_defer_order_created_until_payment,
        )
        from apps.notifications.services.transactional import schedule_payment_captured_email

        schedule_payment_captured_email(order_public_id=payment.order.public_id)
        if should_defer_order_created_until_payment(payment.order):
            from apps.notifications.services.transactional import schedule_order_created_email

            schedule_order_created_email(order_public_id=payment.order.public_id)
        from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService

        CustomerVolumeDiscountTierService().notify_immediate_tier_after_capture(
            order=payment.order,
            actor=actor,
            source=f"{source}.payment_captured",
        )
        self._release_production_after_payment(order=payment.order, actor=actor, source=source)
        return payment.order, payment, invoice

    def _release_production_after_payment(self, *, order, actor, source: str) -> None:
        """Après capture CB atelier : s'assure qu'un OF existe et journalise le déblocage."""
        if order.billing_mode != Order.BillingMode.IMMEDIATE:
            return
        if not order.uses_atelier_pricing():
            return
        from apps.production.services.workflow import ProductionWorkflowService

        job = ProductionWorkflowService().get_or_create_for_order(order=order)
        record_event(
            action="production.unlocked_after_payment",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=job,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "production_job_public_id": str(job.public_id),
                "production_status": job.status,
                "source": source,
            },
        )

    def _get_customer_order(self, *, customer, order_public_id):
        return (
            Order.objects.select_related("customer")
            .filter(customer=customer, public_id=order_public_id)
            .first()
        )

    def _resolve_payment(
        self,
        *,
        order_public_id,
        provider_payment_id: str,
        payment_public_id=None,
    ):
        queryset = Payment.objects.select_related("order", "order__customer").filter(
            order__public_id=order_public_id
        )
        if payment_public_id:
            queryset = queryset.filter(public_id=payment_public_id)
        if provider_payment_id:
            queryset = queryset.filter(
                models_Q_paypal_or_stripe(provider_payment_id=provider_payment_id)
            )
        return queryset.order_by("-created_at").first()

    def _get_gateway(self, *, provider: str | None = None) -> PaymentGateway:
        if self.gateway is not None:
            # Fake/injected gateway (tests) — honour unless provider mismatch on real gateways.
            injected_provider = getattr(self.gateway, "provider", None)
            if provider is None or injected_provider in {None, provider}:
                return self.gateway
        if not provider:
            raise ValidationError("Provider de paiement manquant.")
        return get_payment_gateway(provider)

    def _apply_provider_ids(
        self,
        *,
        payment: Payment,
        provider_payment_id: str,
        provider_capture_id: str = "",
    ) -> None:
        if payment.provider == Payment.Provider.STRIPE:
            if provider_payment_id:
                payment.stripe_checkout_session_id = provider_payment_id
            if provider_capture_id:
                payment.stripe_payment_intent_id = provider_capture_id
            return
        if provider_payment_id:
            payment.paypal_order_id = provider_payment_id
        if provider_capture_id:
            payment.paypal_capture_id = provider_capture_id

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
                "provider": payment.provider,
                "source": source,
            },
        )
        raise ValidationError(payment.last_error_message)


def models_Q_paypal_or_stripe(*, provider_payment_id: str):
    from django.db.models import Q

    return Q(paypal_order_id=provider_payment_id) | Q(
        stripe_checkout_session_id=provider_payment_id
    )
