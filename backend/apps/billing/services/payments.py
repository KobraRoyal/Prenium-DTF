from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from uuid import uuid5

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
    ACTIVE_CAPTURE_STATUSES = frozenset(
        {
            Payment.Status.PENDING,
            Payment.Status.APPROVED,
        }
    )
    FINANCIAL_STATUSES = frozenset(
        {
            Payment.Status.CAPTURED,
            Payment.Status.CAPTURED_REVIEW,
        }
    )

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
        context_digest = self._checkout_context_digest(
            success_url=success_url,
            cancel_url=cancel_url,
        )
        blocked_ambiguous_payment = None
        with transaction.atomic():
            order = self._get_customer_order(
                customer=customer,
                order_public_id=order_public_id,
                for_update=True,
            )
            if order is None:
                return None, None
            self._validate_order_can_start_payment(order=order)

            injected_provider = getattr(self.gateway, "provider", None) if self.gateway else None
            if injected_provider and (not provider or provider == injected_provider):
                resolved_provider = injected_provider
            else:
                resolved_provider = resolve_online_provider(
                    customer=customer,
                    requested_provider=provider,
                )

            if Payment.objects.filter(
                order=order,
                status__in=self.FINANCIAL_STATUSES,
            ).exists():
                raise ValidationError("Cette commande possède déjà un règlement financier.")

            active_payments = list(
                Payment.objects.select_for_update()
                .filter(order=order, status__in=self.ACTIVE_CAPTURE_STATUSES)
                .order_by("pk")
            )
            payment = self._matching_active_payment(
                payments=active_payments,
                provider=resolved_provider,
                amount=order.total_amount,
                currency=order.currency,
                context_digest=context_digest,
            )
            if payment is None:
                blocked_ambiguous_payment = next(
                    (
                        active_payment
                        for active_payment in active_payments
                        if active_payment.capture_resolution_required
                    ),
                    None,
                )
                if blocked_ambiguous_payment is None:
                    self._cancel_locked_payments(
                        payments=active_payments,
                        actor=actor,
                        source=source,
                        reason="superseded",
                    )
                    payment = Payment.objects.create(
                        order=order,
                        created_by=(actor if getattr(actor, "is_authenticated", False) else None),
                        provider=resolved_provider,
                        status=Payment.Status.PENDING,
                        amount=order.total_amount,
                        currency=str(order.currency or "").strip().upper(),
                        source=source,
                        request_snapshot={
                            "order_public_id": str(order.public_id),
                            "customer_public_id": str(order.customer.public_id),
                            "amount": f"{order.total_amount:.2f}",
                            "currency": str(order.currency or "").strip().upper(),
                            "provider": resolved_provider,
                            "checkout_context_sha256": context_digest,
                        },
                    )

        if blocked_ambiguous_payment is not None:
            message = (
                "La confirmation du paiement précédent est indéterminée. "
                "Aucun autre paiement ne peut être lancé avant rapprochement."
            )
            metadata = self._payment_audit_metadata(
                payment=blocked_ambiguous_payment,
                source=source,
            )
            metadata["reason"] = "capture_resolution_required"
            record_event(
                action="billing.payment_initiation_rejected",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=blocked_ambiguous_payment,
                status=AuditLogEntry.Status.FAILURE,
                message=message,
                metadata=metadata,
            )
            raise ValidationError(message)

        return self._create_checkout_for_attempt(
            payment_public_id=payment.public_id,
            actor=actor,
            source=source,
            success_url=success_url,
            cancel_url=cancel_url,
        )

    def confirm_capture(
        self,
        *,
        order_public_id,
        paypal_order_id: str = "",
        payment_public_id=None,
        provider_payment_id: str = "",
        expected_provider: str | None = None,
        actor=None,
        source: str,
    ):
        resolved_provider_payment_id = (provider_payment_id or paypal_order_id or "").strip()
        resolved_provider = expected_provider
        if paypal_order_id:
            if expected_provider and expected_provider != Payment.Provider.PAYPAL:
                raise ValidationError("Provider incohérent pour cet identifiant PayPal.")
            resolved_provider = Payment.Provider.PAYPAL

        deferred_error = ""
        captured_payment_id = None
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .filter(public_id=order_public_id)
                .first()
            )
            if order is None:
                return None, None, None
            payment = self._resolve_payment(
                order=order,
                provider_payment_id=resolved_provider_payment_id,
                payment_public_id=payment_public_id,
                provider=resolved_provider,
                for_update=True,
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
                    metadata=self._payment_audit_metadata(payment=payment, source=source),
                )
                return payment.order, payment, invoice

            if payment.status == Payment.Status.CAPTURED_REVIEW:
                deferred_error = (
                    "Cette capture est déjà en vérification manuelle. Aucun nouveau débit "
                    "n'a été demandé."
                )
                self._record_capture_rejected_locked(
                    payment=payment,
                    actor=actor,
                    source=source,
                    message=deferred_error,
                    reason="captured_review",
                )
            elif payment.status not in self.ACTIVE_CAPTURE_STATUSES:
                deferred_error = "Cette tentative de paiement n'est plus active."
                self._record_capture_rejected_locked(
                    payment=payment,
                    actor=actor,
                    source=source,
                    message=deferred_error,
                    reason="inactive_attempt",
                )
            elif (
                Payment.objects.select_for_update()
                .filter(
                    order=order,
                    status__in=self.FINANCIAL_STATUSES,
                )
                .exclude(pk=payment.pk)
                .exists()
            ):
                deferred_error = "Cette commande possède déjà un règlement financier."
                self._record_capture_rejected_locked(
                    payment=payment,
                    actor=actor,
                    source=source,
                    message=deferred_error,
                    reason="order_already_settled",
                )
            else:
                order_mismatch = self._payment_order_mismatch(payment=payment, order=order)
                if order_mismatch:
                    self._mark_failed_locked(
                        payment=payment,
                        actor=actor,
                        source=source,
                        message=order_mismatch,
                    )
                    deferred_error = order_mismatch
                else:
                    gateway = self._get_gateway(provider=payment.provider)
                    try:
                        result = gateway.confirm_checkout(
                            provider_payment_id=(
                                payment.provider_payment_id or resolved_provider_payment_id
                            ),
                            idempotency_key=self._provider_idempotency_key(
                                payment=payment,
                                operation="capture",
                            ),
                        )
                    except PaymentGatewayError as exc:
                        deferred_error = str(exc).strip() or "Capture provider indéterminée."
                        self._record_capture_retryable_locked(
                            payment=payment,
                            actor=actor,
                            source=source,
                            message=deferred_error,
                        )
                    else:
                        capture_status = str(result.status).upper()
                        if capture_status != "COMPLETED":
                            deferred_error = (
                                f"{payment.provider} capture status is '{result.status}'."
                            )
                            self._record_capture_retryable_locked(
                                payment=payment,
                                actor=actor,
                                source=source,
                                message=deferred_error,
                            )
                        else:
                            review_message = self._capture_review_message(
                                payment=payment,
                                provider_capture_id=result.provider_capture_id,
                                amount_total_cents=result.amount_total_cents,
                                currency=result.currency,
                            )
                            if review_message:
                                deferred_error = review_message
                                self._mark_capture_review_locked(
                                    payment=payment,
                                    provider_capture_id=result.provider_capture_id,
                                    provider_payload=result.payload,
                                    actor=actor,
                                    source=source,
                                    message=review_message,
                                )
                            else:
                                self._mark_captured_locked(
                                    payment=payment,
                                    provider_capture_id=result.provider_capture_id,
                                    provider_payload=result.payload,
                                    actor=actor,
                                    source=source,
                                )
                                captured_payment_id = payment.pk

        if captured_payment_id is not None:
            captured_payment = Payment.objects.select_related("order", "order__customer").get(
                pk=captured_payment_id
            )
            return self._complete_captured_payment(
                payment=captured_payment,
                actor=actor,
                source=source,
            )
        if deferred_error:
            raise ValidationError(deferred_error)
        return None, None, None

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
        captured_payment_id = None
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .filter(
                    payments__provider=Payment.Provider.STRIPE,
                    payments__stripe_checkout_session_id=checkout_session_id,
                )
                .first()
            )
            if order is None:
                return None, None, None
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .filter(
                    order=order,
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
                metadata = self._payment_audit_metadata(payment=payment, source=source)
                metadata["stripe_event_id"] = event_id
                record_event(
                    action="billing.payment_capture_idempotent",
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    target=payment,
                    metadata=metadata,
                )
                return payment.order, payment, invoice
            if payment.status == Payment.Status.CAPTURED_REVIEW:
                return payment.order, payment, None

            other_settlement = (
                Payment.objects.filter(
                    order=order,
                    status__in=self.FINANCIAL_STATUSES,
                )
                .exclude(pk=payment.pk)
                .first()
            )
            if other_settlement is not None:
                message = (
                    "Stripe signale un paiement alors que la commande possède déjà un autre "
                    "règlement financier."
                )
                payment.last_error_message = message[:255]
                payment.save(update_fields=["last_error_message", "updated_at"])
                self._record_capture_rejected_locked(
                    payment=payment,
                    actor=actor,
                    source=source,
                    message=message,
                    reason="stripe_settlement_conflict",
                )
                return payment.order, payment, None

            order_mismatch = self._payment_order_mismatch(payment=payment, order=order)
            provider_capture_id = payment_intent_id or payment.stripe_payment_intent_id
            provider_payload = payload if isinstance(payload, dict) else {}
            amount_total_cents = self._coerce_amount_cents(provider_payload.get("amount_total"))
            provider_review = self._capture_review_message(
                payment=payment,
                provider_capture_id=provider_capture_id,
                amount_total_cents=amount_total_cents,
                currency=provider_payload.get("currency"),
            )
            if (
                payment.status not in self.ACTIVE_CAPTURE_STATUSES
                or order_mismatch
                or provider_review
            ):
                message = order_mismatch or (
                    "Stripe signale un paiement sur une tentative locale inactive."
                    if payment.status not in self.ACTIVE_CAPTURE_STATUSES
                    else provider_review
                )
                self._mark_capture_review_locked(
                    payment=payment,
                    provider_capture_id=provider_capture_id,
                    provider_payload=provider_payload or payment.provider_payload,
                    actor=actor,
                    source=source,
                    message=message,
                )
                return payment.order, payment, None

            self._mark_captured_locked(
                payment=payment,
                provider_capture_id=provider_capture_id,
                provider_payload=provider_payload or payment.provider_payload,
                actor=actor,
                source=source,
                extra_metadata={"stripe_event_id": event_id} if event_id else None,
            )
            captured_payment_id = payment.pk

        captured_payment = Payment.objects.select_related("order", "order__customer").get(
            pk=captured_payment_id
        )
        return self._complete_captured_payment(
            payment=captured_payment,
            actor=actor,
            source=source,
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
            Order.objects.select_for_update().get(pk=payment.order_id)
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            if payment.status == Payment.Status.CAPTURED and payment.provider_capture_id:
                captured_payment = payment
            else:
                captured_payment = self._mark_captured_locked(
                    payment=payment,
                    provider_capture_id=provider_capture_id,
                    provider_payload=provider_payload,
                    actor=actor,
                    source=source,
                    extra_metadata=extra_metadata,
                )

        return self._complete_captured_payment(
            payment=captured_payment,
            actor=actor,
            source=source,
        )

    def _mark_captured_locked(
        self,
        *,
        payment: Payment,
        provider_capture_id: str,
        provider_payload: dict,
        actor,
        source: str,
        extra_metadata: dict | None = None,
    ) -> Payment:
        order = payment.order
        if (
            Payment.objects.filter(
                order=order,
                status__in=self.FINANCIAL_STATUSES,
            )
            .exclude(pk=payment.pk)
            .exists()
        ):
            raise ValidationError("Cette commande possède déjà un règlement financier.")
        if payment.status not in self.ACTIVE_CAPTURE_STATUSES:
            raise ValidationError("Cette tentative de paiement n'est plus active.")

        payment.status = Payment.Status.CAPTURED
        self._apply_provider_ids(
            payment=payment,
            provider_payment_id=payment.provider_payment_id,
            provider_capture_id=provider_capture_id or payment.provider_capture_id,
        )
        payment.provider_payload = provider_payload
        payment.captured_at = timezone.now()
        payment.last_error_message = ""
        request_snapshot = (
            dict(payment.request_snapshot) if isinstance(payment.request_snapshot, dict) else {}
        )
        request_snapshot.pop("capture_resolution_required", None)
        payment.request_snapshot = request_snapshot
        payment.save(
            update_fields=[
                "status",
                "paypal_capture_id",
                "stripe_payment_intent_id",
                "provider_payload",
                "captured_at",
                "last_error_message",
                "request_snapshot",
                "updated_at",
            ]
        )
        metadata = self._payment_audit_metadata(payment=payment, source=source)
        metadata["provider_capture_id"] = payment.provider_capture_id
        if extra_metadata:
            metadata.update(extra_metadata)
        record_event(
            action="billing.payment_captured",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            metadata=metadata,
        )
        return payment

    def _complete_captured_payment(
        self,
        *,
        payment: Payment,
        actor,
        source: str,
    ):
        invoice = self.invoice_service.ensure_invoice_for_captured_payment(
            order=payment.order,
            payment=payment,
            source=source,
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

    def cancel_open_payment_for_order(
        self,
        *,
        order_public_id,
        provider: str | None = None,
        provider_payment_id: str = "",
        actor=None,
        source: str,
    ):
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .filter(public_id=order_public_id)
                .first()
            )
            if order is None:
                return None, None
            payments = Payment.objects.select_for_update().filter(
                order=order,
                status__in=self.ACTIVE_CAPTURE_STATUSES,
            )
            if provider:
                payments = payments.filter(provider=provider)
            if provider_payment_id:
                if provider == Payment.Provider.PAYPAL:
                    payments = payments.filter(paypal_order_id=provider_payment_id)
                elif provider == Payment.Provider.STRIPE:
                    payments = payments.filter(stripe_checkout_session_id=provider_payment_id)
                else:
                    payments = payments.filter(
                        models_Q_paypal_or_stripe(
                            provider_payment_id=provider_payment_id,
                        )
                    )
            locked = list(payments.order_by("-created_at", "-pk")[:1])
            if locked and locked[0].capture_resolution_required:
                return order, locked[0]
            self._cancel_locked_payments(
                payments=locked,
                actor=actor,
                source=source,
                reason="user_cancelled",
            )
            return order, locked[0] if locked else None

    def _get_customer_order(self, *, customer, order_public_id, for_update: bool = False):
        queryset = Order.objects.select_related("customer")
        if for_update:
            queryset = queryset.select_for_update()
        return queryset.filter(customer=customer, public_id=order_public_id).first()

    def _resolve_payment(
        self,
        *,
        order,
        provider_payment_id: str,
        payment_public_id=None,
        provider: str | None = None,
        for_update: bool = False,
    ):
        queryset = Payment.objects.select_related("order", "order__customer").filter(order=order)
        if for_update:
            queryset = queryset.select_for_update()
        if payment_public_id:
            queryset = queryset.filter(public_id=payment_public_id)
        if provider:
            queryset = queryset.filter(provider=provider)
        if provider_payment_id:
            if provider == Payment.Provider.PAYPAL:
                queryset = queryset.filter(paypal_order_id=provider_payment_id)
            elif provider == Payment.Provider.STRIPE:
                queryset = queryset.filter(stripe_checkout_session_id=provider_payment_id)
            else:
                queryset = queryset.filter(
                    models_Q_paypal_or_stripe(provider_payment_id=provider_payment_id)
                )
        return queryset.order_by("-created_at").first()

    def _create_checkout_for_attempt(
        self,
        *,
        payment_public_id,
        actor,
        source: str,
        success_url: str,
        cancel_url: str,
    ):
        deferred_error = ""
        resolved_order = None
        resolved_payment = None
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .filter(payments__public_id=payment_public_id)
                .first()
            )
            if order is None:
                return None, None
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(order=order, public_id=payment_public_id)
            )
            resolved_order = order
            resolved_payment = payment

            if payment.provider_payment_id and payment.approval_url:
                record_event(
                    action="billing.payment_initiation_idempotent",
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    target=payment,
                    metadata=self._payment_audit_metadata(payment=payment, source=source),
                )
                return order, payment
            if payment.status not in self.ACTIVE_CAPTURE_STATUSES:
                raise ValidationError("Cette tentative de paiement n'est plus active.")
            if (
                Payment.objects.filter(
                    order=order,
                    status__in=self.FINANCIAL_STATUSES,
                )
                .exclude(pk=payment.pk)
                .exists()
            ):
                raise ValidationError("Cette commande possède déjà un règlement financier.")

            order_mismatch = self._payment_order_mismatch(payment=payment, order=order)
            if order_mismatch:
                self._mark_failed_locked(
                    payment=payment,
                    actor=actor,
                    source=source,
                    message=order_mismatch,
                )
                deferred_error = order_mismatch
            else:
                gateway = self._get_gateway(provider=payment.provider)
                try:
                    result = gateway.create_checkout(
                        order=order,
                        success_url=success_url,
                        cancel_url=cancel_url,
                        idempotency_key=self._provider_idempotency_key(
                            payment=payment,
                            operation="create",
                        ),
                    )
                except PaymentGatewayError as exc:
                    deferred_error = str(exc).strip() or "Création du paiement impossible."
                    self._mark_failed_locked(
                        payment=payment,
                        actor=actor,
                        source=source,
                        message=deferred_error,
                    )
                else:
                    if not result.provider_payment_id or not result.checkout_url:
                        deferred_error = "Le provider a retourné un checkout incomplet."
                        self._mark_failed_locked(
                            payment=payment,
                            actor=actor,
                            source=source,
                            message=deferred_error,
                        )
                    else:
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
                            actor=(actor if getattr(actor, "is_authenticated", False) else None),
                            target=payment,
                            metadata=self._payment_audit_metadata(
                                payment=payment,
                                source=source,
                            ),
                        )

        if deferred_error:
            raise ValidationError(deferred_error)
        return resolved_order, resolved_payment

    @staticmethod
    def _checkout_context_digest(*, success_url: str, cancel_url: str) -> str:
        canonical = f"{str(success_url).strip()}\n{str(cancel_url).strip()}"
        return sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _matching_active_payment(
        *,
        payments,
        provider: str,
        amount,
        currency: str,
        context_digest: str,
    ):
        expected_currency = str(currency or "").strip().upper()
        expected_amount = Decimal(amount)
        for payment in payments:
            snapshot = payment.request_snapshot or {}
            if (
                payment.provider == provider
                and Decimal(payment.amount) == expected_amount
                and str(payment.currency or "").strip().upper() == expected_currency
                and snapshot.get("checkout_context_sha256") == context_digest
            ):
                return payment
        return None

    def _cancel_locked_payments(
        self,
        *,
        payments,
        actor,
        source: str,
        reason: str,
    ) -> None:
        for payment in payments:
            payment.status = Payment.Status.CANCELLED
            payment.last_error_message = ""
            payment.save(update_fields=["status", "last_error_message", "updated_at"])
            metadata = self._payment_audit_metadata(payment=payment, source=source)
            metadata["reason"] = reason
            record_event(
                action="billing.payment_cancelled",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=payment,
                metadata=metadata,
            )

    @staticmethod
    def _validate_order_can_start_payment(*, order) -> None:
        if order.billing_mode == Order.BillingMode.DEFERRED:
            raise ValidationError(
                "Les commandes en facturation différée ne sont pas payées en ligne."
            )
        if order.total_amount <= 0:
            raise ValidationError("Montant de commande invalide pour un paiement.")

    @staticmethod
    def _payment_order_mismatch(*, payment, order) -> str:
        payment_currency = str(payment.currency or "").strip().upper()
        order_currency = str(order.currency or "").strip().upper()
        if Decimal(payment.amount) != Decimal(order.total_amount) or (
            payment_currency != order_currency
        ):
            return "Le montant ou la devise de la commande a changé depuis le checkout."
        return ""

    def _get_gateway(self, *, provider: str | None = None) -> PaymentGateway:
        if self.gateway is not None:
            # Fake/injected gateway (tests) — honour unless provider mismatch on real gateways.
            injected_provider = getattr(self.gateway, "provider", None)
            if provider is None or injected_provider in {None, provider}:
                return self.gateway
        if not provider:
            raise ValidationError("Provider de paiement manquant.")
        return get_payment_gateway(provider)

    @staticmethod
    def _provider_idempotency_key(*, payment: Payment, operation: str) -> str:
        """Clé stable par tentative et opération, compatible avec la limite PayPal."""
        return str(uuid5(payment.public_id, f"payment:{operation}"))

    @staticmethod
    def _capture_review_message(
        *,
        payment,
        provider_capture_id: str,
        amount_total_cents: int | None,
        currency: str | None,
    ) -> str:
        provider_label = "PayPal" if payment.provider == Payment.Provider.PAYPAL else "Stripe"
        if not str(provider_capture_id or "").strip():
            return f"{provider_label} n'a pas retourné l'identifiant de capture."

        expected_cents = int(
            (Decimal(payment.amount) * Decimal("100")).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
        captured_cents = amount_total_cents
        captured_currency = str(currency or "").strip().upper()
        expected_currency = str(payment.currency or "").strip().upper()
        if captured_cents is None or not captured_currency:
            return f"{provider_label} n'a pas retourné le montant capturé complet."
        if captured_cents != expected_cents or captured_currency != expected_currency:
            return (
                f"Le montant ou la devise confirmé par {provider_label} "
                "ne correspond pas à la commande."
            )
        return ""

    @staticmethod
    def _coerce_amount_cents(value) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _record_capture_retryable_locked(
        self,
        *,
        payment,
        actor,
        source: str,
        message: str,
    ) -> None:
        payment.last_error_message = str(message).strip()[:255]
        request_snapshot = (
            dict(payment.request_snapshot) if isinstance(payment.request_snapshot, dict) else {}
        )
        request_snapshot["capture_resolution_required"] = True
        payment.request_snapshot = request_snapshot
        payment.save(update_fields=["last_error_message", "request_snapshot", "updated_at"])
        record_event(
            action="billing.payment_capture_retryable",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            status=AuditLogEntry.Status.FAILURE,
            message=payment.last_error_message,
            metadata=self._payment_audit_metadata(payment=payment, source=source),
        )

    def _mark_capture_review_locked(
        self,
        *,
        payment,
        provider_capture_id: str,
        provider_payload: dict,
        actor,
        source: str,
        message: str,
    ) -> None:
        payment.status = Payment.Status.CAPTURED_REVIEW
        self._apply_provider_ids(
            payment=payment,
            provider_payment_id=payment.provider_payment_id,
            provider_capture_id=provider_capture_id,
        )
        payment.provider_payload = provider_payload
        payment.captured_at = timezone.now()
        payment.last_error_message = str(message).strip()[:255]
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
        record_event(
            action="billing.payment_capture_review_required",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            status=AuditLogEntry.Status.FAILURE,
            message=payment.last_error_message,
            metadata=self._payment_audit_metadata(payment=payment, source=source),
        )

    def _record_capture_rejected_locked(
        self,
        *,
        payment,
        actor,
        source: str,
        message: str,
        reason: str,
    ) -> None:
        metadata = self._payment_audit_metadata(payment=payment, source=source)
        metadata["reason"] = reason
        record_event(
            action="billing.payment_capture_rejected",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=payment,
            status=AuditLogEntry.Status.FAILURE,
            message=str(message).strip()[:255],
            metadata=metadata,
        )

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

    def _mark_failed_locked(self, *, payment: Payment, actor, source: str, message: str) -> None:
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

    @staticmethod
    def _payment_audit_metadata(*, payment, source: str) -> dict[str, str]:
        return {
            "order_public_id": str(payment.order.public_id),
            "customer_public_id": str(payment.order.customer.public_id),
            "payment_public_id": str(payment.public_id),
            "provider": payment.provider,
            "provider_payment_id": payment.provider_payment_id,
            "source": source,
        }


def models_Q_paypal_or_stripe(*, provider_payment_id: str):
    from django.db.models import Q

    return Q(paypal_order_id=provider_payment_id) | Q(
        stripe_checkout_session_id=provider_payment_id
    )
