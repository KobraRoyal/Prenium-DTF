from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.billing.models import Invoice, Payment
from apps.billing.services.gateways import (
    PaymentGateway,
    PaymentGatewayError,
    PaymentGatewayTransientError,
    get_payment_gateway,
    resolve_online_provider,
)
from apps.billing.services.invoices import InvoiceService
from apps.billing.services.paypal import PayPalBindingError
from apps.customers.models import Customer
from apps.orders.models import Order

IN_FLIGHT_CAPTURE_STATUSES = {"PENDING", "OPEN", "APPROVED", "UNPAID"}
UNKNOWN_CHECKOUT_RETRY_WINDOWS = {
    Payment.Provider.STRIPE: timedelta(hours=23),
    Payment.Provider.PAYPAL: timedelta(hours=5),
}
# Au-delà, le lien approve PayPal est souvent mort alors que l'API dit encore CREATED.
PAYPAL_APPROVAL_REUSE_WINDOW = timedelta(hours=2)
PAYPAL_RESUMABLE_REMOTE_STATES = frozenset({"CREATED", "SAVED", "PAYER_ACTION_REQUIRED"})
_PAID_REMOTE_CHECKOUT_STATES = frozenset({"COMPLETED", "COMPLETE", "PAID"})
_CLIENT_CANCEL_PAYMENT_UNAVAILABLE = (
    "Le paiement en cours n'a pas pu être fermé. Réessayez dans un instant."
)
_CLIENT_CANCEL_PAYMENT_CAPTURED = (
    "Le paiement a été confirmé. Cette commande ne peut plus être supprimée."
)
_REMOTE_CHECKOUT_MISSING_MARKERS = (
    "RESOURCE_NOT_FOUND",
    "INVALID_RESOURCE_ID",
    "No such checkout",
)


def _remote_checkout_missing(exc: PaymentGatewayError) -> bool:
    detail = str(exc)
    return any(marker in detail for marker in _REMOTE_CHECKOUT_MISSING_MARKERS)
STRIPE_FAILURE_RECONCILIATION_MESSAGE = (
    "Échec Stripe signalé ; vérification du règlement en cours avant nouvel essai."
)


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
        self._reconcile_active_checkout(
            customer=customer,
            order_public_id=order_public_id,
            requested_provider=provider,
        )
        # Même ordre de verrouillage que les corrections de métrage et de tarif.
        with transaction.atomic():
            Customer.objects.select_for_update().get(pk=customer.pk)
            order = self._get_customer_order(customer=customer, order_public_id=order_public_id)
            if order is None:
                return None, None
            order = Order.objects.select_for_update().select_related("customer").get(pk=order.pk)
            if order.billing_mode == Order.BillingMode.DEFERRED:
                raise ValidationError(
                    "Les commandes en facturation différée ne sont pas payées en ligne."
                )
            if order.status != Order.Status.SUBMITTED:
                raise ValidationError("Cette commande ne peut pas être payée en ligne.")
            if order.uses_atelier_pricing() and order.pricing_status != Order.PricingStatus.PRICED:
                raise ValidationError(
                    "Le tarif de cette commande doit être confirmé avant paiement."
                )
            if order.total_amount <= 0:
                raise ValidationError("Montant de commande invalide pour un paiement.")
            if Payment.objects.filter(order=order, status=Payment.Status.CAPTURED).exists():
                raise ValidationError("Cette commande est déjà réglée.")

            injected_provider = getattr(self.gateway, "provider", None) if self.gateway else None
            if injected_provider and (not provider or provider == injected_provider):
                resolved_provider = injected_provider
            else:
                resolved_provider = resolve_online_provider(
                    customer=customer,
                    requested_provider=provider,
                )
            existing = (
                Payment.objects.select_for_update()
                .filter(
                    order_id=order.pk,
                    status__in={Payment.Status.PENDING, Payment.Status.APPROVED},
                )
                .order_by("-created_at")
                .first()
            )
            if existing is not None:
                if existing.provider != resolved_provider:
                    raise ValidationError(
                        "Un paiement est déjà ouvert. Terminez-le avant de changer "
                        "de moyen de paiement."
                    )
                if existing.last_error_message == STRIPE_FAILURE_RECONCILIATION_MESSAGE:
                    raise ValidationError(existing.last_error_message)
                if existing.approval_url:
                    return order, existing
                payment = existing
            else:
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
                        "success_url": success_url,
                        "cancel_url": cancel_url,
                    },
                )
            gateway = self._get_gateway(provider=resolved_provider)
            snapshot = payment.request_snapshot or {}
            checkout_success_url = str(snapshot.get("success_url") or success_url)
            checkout_cancel_url = str(snapshot.get("cancel_url") or cancel_url)
        try:
            if payment.provider_payment_id:
                resume = getattr(gateway, "resume_checkout", None)
                if resume is None:
                    raise ValidationError(
                        "Ce paiement doit être rapproché avant de reprendre son lien."
                    )
                result = resume(
                    provider_payment_id=payment.provider_payment_id,
                    order=order,
                    payment_public_id=payment.public_id,
                )
            else:
                retry_window = UNKNOWN_CHECKOUT_RETRY_WINDOWS[resolved_provider]
                if timezone.now() - payment.created_at >= retry_window:
                    raise ValidationError(
                        "La réponse du prestataire manque depuis trop longtemps. "
                        "Contactez le support pour rapprocher cette tentative avant "
                        "tout nouveau paiement."
                    )
                result = gateway.create_checkout(
                    order=order,
                    success_url=checkout_success_url,
                    cancel_url=checkout_cancel_url,
                    idempotency_key=str(payment.public_id),
                )
        except PaymentGatewayTransientError:
            raise
        except PaymentGatewayError as exc:
            # Une erreur HTTP ne prouve pas que la création distante a échoué.
            # Garder la même tentative et la même clé idempotente au prochain essai.
            raise PaymentGatewayTransientError(str(exc)) from exc

        if not result.provider_payment_id:
            raise ValidationError("Le prestataire n'a pas fourni de référence de paiement.")
        with transaction.atomic():
            Order.objects.select_for_update().get(pk=order.pk)
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status == Payment.Status.CAPTURED:
                if payment.provider_payment_id != result.provider_payment_id:
                    raise ValidationError("Référence de paiement incohérente après capture.")
                return order, payment
            if payment.status in (Payment.Status.FAILED, Payment.Status.CANCELLED):
                raise ValidationError("Cette tentative de paiement n'est plus active.")
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
                    "source": source,
                },
            )
        return order, payment

    def _reconcile_active_checkout(self, *, customer, order_public_id, requested_provider):
        order = self._get_customer_order(customer=customer, order_public_id=order_public_id)
        if order is None:
            return
        payment = (
            Payment.objects.filter(
                order=order,
                status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
            )
            .order_by("-created_at")
            .first()
        )
        if payment is None or not payment.provider_payment_id:
            return
        if self.gateway is not None and self.gateway.provider != payment.provider:
            return
        gateway = self._get_gateway(provider=payment.provider)
        # Lien sandbox après bascule live (ou l'inverse) : abandonner sans appeler l'API.
        # Ne s'applique qu'aux vraies URLs PayPal (évite les fakes de tests / hosts internes).
        approval_url = str(payment.approval_url or "")
        paypal_base = str(getattr(settings, "PAYPAL_API_BASE_URL", "") or "")
        if payment.provider == Payment.Provider.PAYPAL and "paypal.com" in approval_url.lower():
            approval_is_sandbox = "sandbox.paypal.com" in approval_url.lower()
            api_is_sandbox = "sandbox" in paypal_base.lower()
            if approval_is_sandbox != api_is_sandbox:
                self._cancel_stale_checkout_payment(
                    order=order,
                    payment=payment,
                    reason="paypal_environment_mismatch",
                    error_message=(
                        "Session PayPal abandonnée après changement d'environnement (sandbox/live)."
                    ),
                )
                return
        inspect = getattr(gateway, "checkout_state", None)
        if inspect is None:
            return
        try:
            state = str(inspect(provider_payment_id=payment.provider_payment_id)).upper()
            switching = bool(requested_provider and requested_provider != payment.provider)
            if state == "OPEN" and payment.provider == Payment.Provider.STRIPE and switching:
                state = str(
                    gateway.expire_checkout(provider_payment_id=payment.provider_payment_id)
                ).upper()
            elif (
                payment.provider == Payment.Provider.PAYPAL
                and state in PAYPAL_RESUMABLE_REMOTE_STATES
                and (
                    switching or timezone.now() - payment.created_at >= PAYPAL_APPROVAL_REUSE_WINDOW
                )
            ):
                self._cancel_stale_checkout_payment(
                    order=order,
                    payment=payment,
                    reason=("provider_switch" if switching else "paypal_approval_stale"),
                    error_message="",
                )
                return
        except PaymentGatewayError as exc:
            detail = str(exc)
            # Référence absente chez le prestataire (annulation client, sandbox, etc.).
            if any(
                marker in detail
                for marker in ("RESOURCE_NOT_FOUND", "INVALID_RESOURCE_ID", "No such checkout")
            ):
                state = "VOIDED"
            elif any(
                marker in detail
                for marker in (
                    "Invalid API Key",
                    "Invalid API key",
                    "401",
                    "Unauthorized",
                    "invalid_api_key",
                )
            ):
                # Clés Stripe mal collées (pk_/sk_ inversées, etc.) : libérer le
                # checkout local pour permettre un nouvel essai / un autre moyen.
                self._cancel_stale_checkout_payment(
                    order=order,
                    payment=payment,
                    reason="provider_auth_failed",
                    error_message=(
                        "Session de paiement abandonnée (identifiants prestataire invalides). "
                        "Vérifiez les clés dans Atelier → Paiements, puis réessayez."
                    ),
                )
                return
            else:
                raise PaymentGatewayTransientError(str(exc)) from exc
        if state == "COMPLETED":
            try:
                self._verify_checkout_binding(gateway=gateway, payment=payment)
            except ValidationError:
                return
            if payment.provider == Payment.Provider.STRIPE:
                self.confirm_stripe_checkout_session(
                    checkout_session_id=payment.provider_payment_id,
                    source="checkout_reconciliation",
                )
            else:
                self.confirm_capture(
                    order_public_id=order.public_id,
                    provider_payment_id=payment.provider_payment_id,
                    source="checkout_reconciliation",
                )
            return
        if state == "APPROVED" and payment.provider == Payment.Provider.PAYPAL:
            try:
                self._verify_checkout_binding(gateway=gateway, payment=payment)
            except ValidationError:
                return
            self.confirm_capture(
                order_public_id=order.public_id,
                provider_payment_id=payment.provider_payment_id,
                source="checkout_reconciliation",
            )
            return
        if state not in {"EXPIRED", "VOIDED"}:
            return
        self._cancel_stale_checkout_payment(
            order=order,
            payment=payment,
            reason="provider_checkout_voided",
            error_message="",
        )

    def _cancel_stale_checkout_payment(
        self,
        *,
        order,
        payment: Payment,
        reason: str,
        error_message: str = "",
    ) -> None:
        with transaction.atomic():
            Order.objects.select_for_update().get(pk=order.pk)
            locked = Payment.objects.select_for_update().get(pk=payment.pk)
            if locked.status not in (Payment.Status.PENDING, Payment.Status.APPROVED):
                return
            locked.status = Payment.Status.CANCELLED
            update_fields = ["status", "updated_at"]
            if error_message:
                locked.last_error_message = error_message
                update_fields.append("last_error_message")
            locked.save(update_fields=update_fields)
            record_event(
                action="billing.payment_checkout_expired",
                target=locked,
                metadata={
                    "order_public_id": str(order.public_id),
                    "payment_public_id": str(locked.public_id),
                    "provider": locked.provider,
                    "provider_payment_id": locked.provider_payment_id,
                    "reason": reason,
                },
            )

    def cancel_open_checkouts_for_order(
        self,
        *,
        order,
        actor=None,
        source: str = "client_portal_cancel",
    ) -> int:
        """Ferme les tentatives locales encore ouvertes après annulation utilisateur."""
        open_payments = list(
            Payment.objects.filter(
                order_id=order.pk,
                status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
            ).order_by("created_at")
        )
        cancelled = 0
        for payment in open_payments:
            with transaction.atomic():
                locked = (
                    Payment.objects.select_for_update()
                    .filter(
                        pk=payment.pk,
                        status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                    )
                    .first()
                )
                if locked is None:
                    continue
                locked.status = Payment.Status.CANCELLED
                locked.last_error_message = "Paiement annulé par le client."
                locked.save(update_fields=("status", "last_error_message", "updated_at"))
                record_event(
                    action="billing.payment_cancelled_by_client",
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    target=locked,
                    metadata={
                        "order_public_id": str(order.public_id),
                        "payment_public_id": str(locked.public_id),
                        "provider": locked.provider,
                        "provider_payment_id": locked.provider_payment_id,
                        "source": source,
                    },
                )
                cancelled += 1
        return cancelled

    def close_open_checkouts_before_client_cancel(
        self,
        *,
        order,
        actor=None,
        source: str,
    ) -> None:
        """Ferme les sessions encore payables avant l'annulation client.

        Une session Stripe ouverte est expirée chez le prestataire. Un règlement
        déjà payé est rapproché localement, puis l'annulation doit être refusée.
        """
        open_payments = list(
            Payment.objects.filter(
                order_id=order.pk,
                status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
            ).order_by("created_at")
        )
        for payment in open_payments:
            remote_id = str(payment.provider_payment_id or "").strip()
            if not remote_id:
                continue
            gateway = self._get_gateway(provider=payment.provider)
            inspect = getattr(gateway, "checkout_state", None)
            if inspect is None:
                continue
            try:
                state = str(inspect(provider_payment_id=remote_id)).upper()
            except PaymentGatewayError as exc:
                if _remote_checkout_missing(exc):
                    continue
                raise ValidationError(_CLIENT_CANCEL_PAYMENT_UNAVAILABLE) from exc
            if state in _PAID_REMOTE_CHECKOUT_STATES:
                self._sync_paid_checkout_for_client_cancel(
                    payment=payment,
                    order=order,
                    actor=actor,
                    source=source,
                )
                raise ValidationError(_CLIENT_CANCEL_PAYMENT_CAPTURED)
            if payment.provider == Payment.Provider.STRIPE and state == "OPEN":
                expire = getattr(gateway, "expire_checkout", None)
                if expire is None:
                    continue
                try:
                    expire(provider_payment_id=remote_id)
                except PaymentGatewayError as exc:
                    if _remote_checkout_missing(exc):
                        continue
                    latest = ""
                    try:
                        latest = str(inspect(provider_payment_id=remote_id)).upper()
                    except PaymentGatewayError:
                        latest = ""
                    if latest in _PAID_REMOTE_CHECKOUT_STATES:
                        self._sync_paid_checkout_for_client_cancel(
                            payment=payment,
                            order=order,
                            actor=actor,
                            source=source,
                        )
                        raise ValidationError(_CLIENT_CANCEL_PAYMENT_CAPTURED) from exc
                    raise ValidationError(_CLIENT_CANCEL_PAYMENT_UNAVAILABLE) from exc
        self.cancel_open_checkouts_for_order(order=order, actor=actor, source=source)

    def _sync_paid_checkout_for_client_cancel(self, *, payment, order, actor, source: str) -> None:
        try:
            if payment.provider == Payment.Provider.STRIPE:
                self.confirm_stripe_checkout_session(
                    checkout_session_id=payment.provider_payment_id,
                    actor=actor,
                    source=source,
                )
                return
            self.confirm_capture(
                order_public_id=order.public_id,
                provider_payment_id=payment.provider_payment_id,
                payment_public_id=payment.public_id,
                actor=actor,
                source=source,
            )
        except (ValidationError, PaymentGatewayError):
            return

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
        if not order_public_id and not resolved_provider_payment_id and not payment_public_id:
            return None, None, None
        payment = self._resolve_payment(
            order_public_id=order_public_id,
            provider_payment_id=resolved_provider_payment_id,
            payment_public_id=payment_public_id,
        )
        if payment is None and payment_public_id and resolved_provider_payment_id:
            try:
                candidate_id = UUID(str(payment_public_id))
            except (TypeError, ValueError, AttributeError):
                candidate_id = None
            if candidate_id:
                candidates = Payment.objects.filter(
                    public_id=candidate_id,
                    provider=Payment.Provider.PAYPAL,
                    status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                )
                if order_public_id:
                    candidates = candidates.filter(order__public_id=order_public_id)
                candidate = candidates.select_related("order").first()
                if candidate and candidate.paypal_order_id in ("", resolved_provider_payment_id):
                    gateway = self._get_gateway(provider=Payment.Provider.PAYPAL)
                    verify_binding = getattr(gateway, "verify_checkout_binding", None)
                    if verify_binding:
                        try:
                            verify_binding(
                                provider_payment_id=resolved_provider_payment_id,
                                payment_public_id=candidate.public_id,
                                order_public_id=candidate.order.public_id,
                                amount=candidate.amount,
                                currency=candidate.currency,
                                allow_legacy_custom_id=False,
                            )
                        except PayPalBindingError as exc:
                            raise ValidationError(str(exc)) from exc
                        except PaymentGatewayError as exc:
                            raise PaymentGatewayTransientError(str(exc)) from exc
                with transaction.atomic():
                    if candidate is not None:
                        Order.objects.select_for_update().get(pk=candidate.order_id)
                    candidate = (
                        Payment.objects.select_for_update()
                        .filter(
                            public_id=candidate_id,
                            provider=Payment.Provider.PAYPAL,
                            status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                            **({"order__public_id": order_public_id} if order_public_id else {}),
                        )
                        .first()
                    )
                    if candidate and candidate.paypal_order_id in (
                        "",
                        resolved_provider_payment_id,
                    ):
                        candidate.paypal_order_id = resolved_provider_payment_id
                        candidate.save(update_fields=("paypal_order_id", "updated_at"))
                        payment = candidate
        if payment is None:
            return None, None, None

        if payment.status == Payment.Status.CAPTURED and payment.provider_capture_id:
            return self._finalize_captured_payment(
                payment=payment,
                provider_capture_id=payment.provider_capture_id,
                provider_payload=payment.provider_payload,
                actor=actor,
                source=source,
            )

        gateway = self._get_gateway(provider=payment.provider)
        try:
            if payment.provider == Payment.Provider.PAYPAL:
                if (
                    payment.amount != payment.order.total_amount
                    or payment.currency.upper() != payment.order.currency.upper()
                ):
                    raise ValidationError(
                        "Le montant de la commande a changé depuis l'ouverture du paiement."
                    )
                verify_binding = getattr(gateway, "verify_checkout_binding", None)
                if verify_binding:
                    verify_binding(
                        provider_payment_id=payment.provider_payment_id
                        or resolved_provider_payment_id,
                        payment_public_id=payment.public_id,
                        order_public_id=payment.order.public_id,
                        amount=payment.amount,
                        currency=payment.currency,
                        allow_legacy_custom_id=True,
                    )
            result = gateway.confirm_checkout(
                provider_payment_id=payment.provider_payment_id or resolved_provider_payment_id
            )
        except PaymentGatewayTransientError:
            raise
        except PayPalBindingError as exc:
            raise ValidationError(str(exc)) from exc
        except PaymentGatewayError as exc:
            raise PaymentGatewayTransientError(str(exc)) from exc

        self._assert_amount_matches(payment=payment, result=result)
        capture_status = str(result.status).upper()
        if capture_status in IN_FLIGHT_CAPTURE_STATUSES:
            return payment.order, payment, None
        if capture_status != "COMPLETED":
            raise ValidationError(f"État du paiement à vérifier : {result.status}.")

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
        payment_public_id: str = "",
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
        if payment is None and payment_public_id:
            with transaction.atomic():
                candidate = (
                    Payment.objects.select_for_update()
                    .select_related("order", "order__customer")
                    .filter(
                        public_id=payment_public_id,
                        provider=Payment.Provider.STRIPE,
                        status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                    )
                    .first()
                )
                if candidate is not None and candidate.stripe_checkout_session_id in (
                    "",
                    checkout_session_id,
                ):
                    self._verify_checkout_binding(
                        gateway=self._get_gateway(provider=Payment.Provider.STRIPE),
                        payment=candidate,
                        provider_payment_id=checkout_session_id,
                    )
                    candidate.stripe_checkout_session_id = checkout_session_id
                    candidate.save(update_fields=("stripe_checkout_session_id", "updated_at"))
                    payment = candidate
        if payment is None:
            return None, None, None

        if payment.status == Payment.Status.CAPTURED and payment.stripe_payment_intent_id:
            return self._finalize_captured_payment(
                payment=payment,
                provider_capture_id=payment.stripe_payment_intent_id,
                provider_payload=payment.provider_payload,
                actor=actor,
                source=source,
                extra_metadata={"stripe_event_id": event_id} if event_id else None,
            )

        gateway = self._get_gateway(provider=Payment.Provider.STRIPE)
        try:
            self._verify_checkout_binding(gateway=gateway, payment=payment)
            result = gateway.confirm_checkout(provider_payment_id=checkout_session_id)
        except PaymentGatewayTransientError:
            raise
        except PaymentGatewayError as exc:
            raise PaymentGatewayTransientError(str(exc)) from exc

        self._assert_amount_matches(payment=payment, result=result)
        capture_status = str(result.status).upper()
        if capture_status in IN_FLIGHT_CAPTURE_STATUSES:
            return payment.order, payment, None
        if capture_status != "COMPLETED":
            raise ValidationError(f"État du paiement à vérifier : {result.status}.")

        return self._finalize_captured_payment(
            payment=payment,
            provider_capture_id=result.provider_capture_id,
            provider_payload=result.payload or payload or payment.provider_payload,
            actor=actor,
            source=source,
            extra_metadata={"stripe_event_id": event_id} if event_id else None,
        )

    def mark_stripe_checkout_failed(
        self,
        *,
        checkout_session_id: str,
        payment_public_id: str = "",
        actor=None,
        source: str,
        message: str,
        event_id: str = "",
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
        if payment is None and payment_public_id:
            with transaction.atomic():
                candidate = (
                    Payment.objects.select_for_update()
                    .filter(
                        public_id=payment_public_id,
                        provider=Payment.Provider.STRIPE,
                        status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                    )
                    .first()
                )
                if candidate and candidate.stripe_checkout_session_id in ("", checkout_session_id):
                    self._verify_checkout_binding(
                        gateway=self._get_gateway(provider=Payment.Provider.STRIPE),
                        payment=candidate,
                        provider_payment_id=checkout_session_id,
                    )
                    candidate.stripe_checkout_session_id = checkout_session_id
                    candidate.save(update_fields=("stripe_checkout_session_id", "updated_at"))
                    payment = candidate
        if payment is None:
            return None
        if payment.status == Payment.Status.CAPTURED:
            return payment
        gateway = self._get_gateway(provider=Payment.Provider.STRIPE)
        self._verify_checkout_binding(gateway=gateway, payment=payment)
        try:
            current = gateway.confirm_checkout(provider_payment_id=checkout_session_id)
        except PaymentGatewayTransientError:
            raise
        except PaymentGatewayError as exc:
            raise PaymentGatewayTransientError(str(exc)) from exc
        if str(current.status).upper() == "COMPLETED":
            # Les webhooks peuvent arriver dans le désordre : l'état actuel du
            # prestataire prime sur l'ancien événement d'échec.
            _, payment, _ = self.confirm_stripe_checkout_session(
                checkout_session_id=checkout_session_id,
                actor=actor,
                source=f"{source}.failure_event_reconciliation",
                event_id=event_id,
            )
            return payment
        if str(current.status).upper() != "EXPIRED":
            return self._hold_stripe_failure_for_reconciliation(
                payment=payment, actor=actor, source=source, event_id=event_id
            )
        try:
            self._mark_failed(payment=payment, actor=actor, source=source, message=message)
        except ValidationError:
            payment.refresh_from_db()
            return payment
        return payment

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
        if not provider_capture_id:
            raise ValidationError("La référence de capture du prestataire est manquante.")
        with transaction.atomic():
            order = (
                Order.objects.select_for_update()
                .select_related("customer")
                .get(pk=payment.order_id)
            )
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            if (
                payment.amount != order.total_amount
                or payment.currency.upper() != order.currency.upper()
            ):
                raise ValidationError(
                    "Le montant de la commande a changé depuis l'ouverture du paiement."
                )
            if (
                Payment.objects.filter(order=order, status=Payment.Status.CAPTURED)
                .exclude(pk=payment.pk)
                .exists()
            ):
                raise ValidationError("Cette commande possède déjà un autre paiement capturé.")
            if payment.status == Payment.Status.CAPTURED and payment.provider_capture_id:
                if payment.provider_capture_id != provider_capture_id:
                    raise ValidationError("Référence de capture incohérente.")
                newly_captured = False
            else:
                if payment.status in (Payment.Status.FAILED, Payment.Status.CANCELLED):
                    raise ValidationError("Cette tentative de paiement n'est plus active.")
                payment.status = Payment.Status.CAPTURED
                self._apply_provider_ids(
                    payment=payment,
                    provider_payment_id=payment.provider_payment_id,
                    provider_capture_id=provider_capture_id,
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
                newly_captured = True
                record_event(
                    action="billing.payment_captured",
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    target=payment,
                    metadata={
                        "order_public_id": str(order.public_id),
                        "customer_public_id": str(order.customer.public_id),
                        "payment_public_id": str(payment.public_id),
                        "provider": payment.provider,
                        "provider_capture_id": payment.provider_capture_id,
                        "source": source,
                        **(extra_metadata or {}),
                    },
                )

        # Le débit confirmé est durable avant PDF/notifications/Atelier. Si une
        # dépendance échoue, le webhook répond 5xx et son retry reprend ici.
        with transaction.atomic():
            order = Order.objects.select_for_update().select_related("customer").get(pk=order.pk)
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            invoice_existed = Invoice.objects.filter(order=order).exists()
            invoice = self.invoice_service.ensure_invoice_for_captured_payment(
                order=order,
                payment=payment,
                source=source,
            )
            if newly_captured or not invoice_existed:
                from apps.customers.services.volume_discounts import (
                    CustomerVolumeDiscountTierService,
                )
                from apps.notifications.services.transactional import (
                    schedule_order_created_email,
                    schedule_payment_captured_email,
                )

                schedule_payment_captured_email(order_public_id=order.public_id)
                schedule_order_created_email(order_public_id=order.public_id)
                CustomerVolumeDiscountTierService().notify_immediate_tier_after_capture(
                    order=order,
                    actor=actor,
                    source=f"{source}.payment_captured",
                )
            self._release_production_after_payment(order=order, actor=actor, source=source)
            return order, payment, invoice

    def _release_production_after_payment(self, *, order, actor, source: str) -> None:
        """Après capture comptant : livre l'OF et la notification à l'Atelier."""
        if order.billing_mode != Order.BillingMode.IMMEDIATE:
            return
        if order.status != Order.Status.SUBMITTED:
            return
        from apps.notifications.services.workshop_push import WorkshopNotificationService
        from apps.production.services.workflow import ProductionWorkflowService

        job = ProductionWorkflowService().get_or_create_for_order(order=order)
        WorkshopNotificationService().publish_order_submitted(
            order=order,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            source=source,
        )
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

    def recover_incomplete_captures(self, *, limit: int = 100) -> dict[str, int]:
        """Rejoue uniquement les effets locaux manquants d'une capture durable."""
        from apps.notifications.models import WorkshopNotificationEvent

        complete_receipt = Invoice.objects.filter(
            order_id=OuterRef("order_id"),
            payment_id=OuterRef("pk"),
            paid_at__isnull=False,
        ).exclude(file="")
        workshop_event = WorkshopNotificationEvent.objects.filter(
            order_id=OuterRef("order_id"),
            event_type=WorkshopNotificationEvent.EventType.ORDER_SUBMITTED,
        )
        cutoff = timezone.now() - timedelta(minutes=2)
        candidates = list(
            Payment.objects.filter(status=Payment.Status.CAPTURED)
            .filter(Q(captured_at__lte=cutoff) | Q(captured_at__isnull=True))
            .annotate(
                _has_complete_receipt=Exists(complete_receipt),
                _has_workshop_event=Exists(workshop_event),
            )
            .filter(
                Q(_has_complete_receipt=False)
                | Q(
                    order__billing_mode=Order.BillingMode.IMMEDIATE,
                    order__status=Order.Status.SUBMITTED,
                    _has_workshop_event=False,
                )
            )
            .select_related("order", "order__customer")
            .order_by("updated_at", "pk")[: max(1, min(limit, 500))]
        )
        recovered = failed = 0
        for payment in candidates:
            try:
                self._finalize_captured_payment(
                    payment=payment,
                    provider_capture_id=payment.provider_capture_id,
                    provider_payload=payment.provider_payload,
                    actor=None,
                    source="payment_recovery",
                )
            except Exception as exc:
                failed += 1
                Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now())
                record_event(
                    action="billing.payment_recovery_failed",
                    target=payment,
                    status=AuditLogEntry.Status.FAILURE,
                    message="Captured payment recovery failed.",
                    metadata={
                        "order_public_id": str(payment.order.public_id),
                        "payment_public_id": str(payment.public_id),
                        "error_type": type(exc).__name__,
                        "source": "payment_recovery",
                    },
                )
            else:
                recovered += 1
        return {"recovered": recovered, "failed": failed}

    def reconcile_active_payments(self, *, limit: int = 100) -> dict[str, int]:
        """Rapproche les sessions distantes sans dépendre du retour client ou webhook."""
        cutoff = timezone.now() - timedelta(minutes=2)
        candidates = list(
            Payment.objects.filter(
                status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                updated_at__lte=cutoff,
            )
            .filter(Q(paypal_order_id__gt="") | Q(stripe_checkout_session_id__gt=""))
            .select_related("order", "order__customer")
            .order_by("updated_at", "pk")[: max(1, min(limit, 500))]
        )
        reconciled = failed = 0
        for payment in candidates:
            if not payment.provider_payment_id:
                continue
            try:
                self._reconcile_active_checkout(
                    customer=payment.order.customer,
                    order_public_id=payment.order.public_id,
                    requested_provider=payment.provider,
                )
            except Exception as exc:
                failed += 1
                Payment.objects.filter(pk=payment.pk).update(updated_at=timezone.now())
                record_event(
                    action="billing.payment_reconciliation_failed",
                    target=payment,
                    status=AuditLogEntry.Status.FAILURE,
                    message="Provider payment reconciliation failed.",
                    metadata={
                        "order_public_id": str(payment.order.public_id),
                        "payment_public_id": str(payment.public_id),
                        "error_type": type(exc).__name__,
                        "source": "payment_reconciliation",
                    },
                )
            else:
                reconciled += 1
                Payment.objects.filter(
                    pk=payment.pk,
                    status__in=(Payment.Status.PENDING, Payment.Status.APPROVED),
                ).update(updated_at=timezone.now())
        return {"reconciled": reconciled, "failed": failed}

    def _verify_checkout_binding(
        self, *, gateway, payment: Payment, provider_payment_id: str = ""
    ) -> None:
        verify = getattr(gateway, "verify_checkout_binding", None)
        if verify is None:
            return
        remote_id = provider_payment_id or payment.provider_payment_id
        try:
            if payment.provider == Payment.Provider.PAYPAL:
                verify(
                    provider_payment_id=remote_id,
                    payment_public_id=payment.public_id,
                    order_public_id=payment.order.public_id,
                    amount=payment.amount,
                    currency=payment.currency,
                    allow_legacy_custom_id=True,
                )
            else:
                verify(
                    provider_payment_id=remote_id,
                    payment_public_id=payment.public_id,
                    order_public_id=payment.order.public_id,
                    customer_public_id=payment.order.customer.public_id,
                    amount=payment.amount,
                    currency=payment.currency,
                    allow_legacy_missing_payment_id=(
                        bool(payment.stripe_checkout_session_id)
                        and payment.stripe_checkout_session_id == remote_id
                    ),
                )
        except PaymentGatewayTransientError:
            raise
        except PaymentGatewayError as exc:
            raise ValidationError(str(exc)) from exc

    def close_unknown_checkout_after_reconciliation(
        self,
        *,
        payment_public_id,
        actor,
        resolution: str,
        evidence: str,
        reason: str,
        management_command: bool = False,
    ) -> Payment:
        """Fermeture manuelle auditée après preuve qu'aucun checkout ne reste payable."""
        if not management_command and not (
            getattr(actor, "is_active", False)
            and getattr(actor, "is_staff", False)
            and actor.has_perm("billing.confirm_payment")
        ):
            raise ValidationError("Permission de rapprochement de paiement requise.")
        if resolution not in {"no_remote_checkout", "remote_closed"}:
            raise ValidationError("Résultat du rapprochement prestataire invalide.")
        clean_evidence = str(evidence or "").strip()
        clean_reason = str(reason or "").strip()
        if len(clean_evidence) < 12 or len(clean_reason) < 12:
            raise ValidationError("Preuve externe et motif détaillés requis.")
        payment = (
            Payment.objects.select_related("order").filter(public_id=payment_public_id).first()
        )
        if payment is None:
            raise ValidationError("Tentative de paiement introuvable.")
        with transaction.atomic():
            order = Order.objects.select_for_update().get(pk=payment.order_id)
            payment = Payment.objects.select_for_update().get(pk=payment.pk)
            if payment.status not in (
                Payment.Status.PENDING,
                Payment.Status.APPROVED,
                Payment.Status.FAILED,
                Payment.Status.CANCELLED,
            ):
                raise ValidationError("Cette tentative ne peut pas être rapprochée.")
            if AuditLogEntry.objects.filter(
                action="billing.unknown_checkout_manually_closed",
                target_model="Payment",
                target_public_id=payment.public_id,
                status=AuditLogEntry.Status.SUCCESS,
            ).exists():
                raise ValidationError("Cette tentative a déjà été rapprochée.")
            if payment.provider_payment_id or payment.approval_url:
                raise ValidationError(
                    "La référence prestataire existe : vérifier son état distant."
                )
            if Payment.objects.filter(order=order, status=Payment.Status.CAPTURED).exists():
                raise ValidationError("Cette commande possède déjà un paiement capturé.")
            retry_window = UNKNOWN_CHECKOUT_RETRY_WINDOWS[payment.provider]
            if timezone.now() - payment.created_at < retry_window:
                raise ValidationError("La fenêtre de rapprochement automatique est encore ouverte.")
            payment.status = Payment.Status.CANCELLED
            payment.last_error_message = "Fermée après rapprochement du prestataire."
            payment.save(update_fields=("status", "last_error_message", "updated_at"))
            record_event(
                action="billing.unknown_checkout_manually_closed",
                actor=actor,
                target=payment,
                metadata={
                    "order_public_id": str(order.public_id),
                    "customer_public_id": str(order.customer.public_id),
                    "payment_public_id": str(payment.public_id),
                    "provider": payment.provider,
                    "resolution": resolution,
                    "evidence": clean_evidence[:255],
                    "reason": clean_reason[:255],
                    "source": "management_command" if management_command else "staff_action",
                },
            )
        return payment

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
        queryset = Payment.objects.select_related("order", "order__customer")
        if order_public_id:
            queryset = queryset.filter(order__public_id=order_public_id)
        if payment_public_id:
            queryset = queryset.filter(public_id=payment_public_id)
        if provider_payment_id:
            queryset = queryset.filter(
                models_Q_paypal_or_stripe(provider_payment_id=provider_payment_id)
            )
        return queryset.order_by("-created_at").first()

    def _assert_amount_matches(self, *, payment: Payment, result) -> None:
        expected_cents = int((Decimal(payment.amount) * Decimal("100")).quantize(Decimal("1")))
        actual_cents = getattr(result, "amount_total_cents", None)
        if (
            payment.provider == Payment.Provider.STRIPE
            and str(result.status).upper() == "COMPLETED"
        ):
            if actual_cents is None or not getattr(result, "currency", None):
                raise ValidationError("Montant ou devise Stripe absents de la confirmation.")
        if actual_cents is not None and int(actual_cents) != expected_cents:
            raise ValidationError(
                f"Montant {payment.provider} incohérent "
                f"({actual_cents} cents vs {expected_cents} attendus)."
            )
        actual_currency = str(getattr(result, "currency", None) or "").strip().upper()
        if actual_currency and actual_currency != str(payment.currency or "").upper():
            raise ValidationError(
                f"Devise {payment.provider} incohérente ({actual_currency} vs {payment.currency})."
            )

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

    def _hold_stripe_failure_for_reconciliation(
        self, *, payment: Payment, actor, source: str, event_id: str
    ) -> Payment:
        message = STRIPE_FAILURE_RECONCILIATION_MESSAGE
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            if payment.status not in (Payment.Status.PENDING, Payment.Status.APPROVED):
                return payment
            if payment.last_error_message == message:
                return payment
            payment.last_error_message = message
            payment.save(update_fields=["last_error_message", "updated_at"])
            record_event(
                action="billing.stripe_failure_pending_reconciliation",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=payment,
                status=AuditLogEntry.Status.FAILURE,
                message=message,
                metadata={
                    "order_public_id": str(payment.order.public_id),
                    "payment_public_id": str(payment.public_id),
                    "stripe_event_id": event_id,
                    "source": source,
                },
            )
            return payment

    def _mark_failed(self, *, payment: Payment, actor, source: str, message: str):
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .select_related("order", "order__customer")
                .get(pk=payment.pk)
            )
            if payment.status == Payment.Status.CAPTURED:
                raise ValidationError("Ce paiement a déjà été capturé.")
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
