from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.views import View

from apps.billing.models import Payment
from apps.customers.models import Customer
from apps.orders.models import Order
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    ClientOwnerRequiredMixin,
    ScopedCustomerMixin,
    billing_service,
    order_service,
)


def _absolute_portal_url(path: str) -> str:
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{path}"


class _ClientOrderLookupMixin(ScopedCustomerMixin):
    def get_order_or_404(self, order_public_id):
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return order


class ClientOrderPaymentInitiateView(ClientOwnerRequiredMixin, _ClientOrderLookupMixin, View):
    """Démarre un checkout PayPal/Stripe pour une commande en paiement immédiat."""

    def post(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        if order.billing_mode == Order.BillingMode.DEFERRED:
            raise Http404

        provider = str(request.POST.get("provider", "")).strip().lower() or None
        success_path = reverse(
            "portal:client-order-payment-return",
            kwargs={
                "customer_public_id": customer_public_id,
                "order_public_id": order_public_id,
            },
        )
        success_url = _absolute_portal_url(
            f"{success_path}?status=success&session_id={{CHECKOUT_SESSION_ID}}"
        )
        cancel_url = _absolute_portal_url(f"{success_path}?status=cancel")

        try:
            _order, payment = billing_service.initiate_payment_for_customer_order(
                customer=self.customer,
                order_public_id=order.public_id,
                actor=request.user,
                source="client_portal",
                provider=provider,
                success_url=success_url,
                cancel_url=cancel_url,
            )
        except DjangoValidationError as error:
            message = "; ".join(error.messages) if hasattr(error, "messages") else str(error)
            messages.error(request, message)
            billing_url = reverse(
                "portal:client-order-panel-billing",
                kwargs={
                    "customer_public_id": customer_public_id,
                    "order_public_id": order_public_id,
                },
            )
            response = HttpResponseRedirect(billing_url)
            return with_toast(response, message=message, variant="error")

        if payment is None or not payment.approval_url:
            raise Http404
        return HttpResponseRedirect(payment.approval_url)


class ClientOrderPaymentReturnView(ClientOwnerRequiredMixin, _ClientOrderLookupMixin, View):
    """Retour provider : capture/confirm + redirection panneau facture."""

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        status = str(request.GET.get("status", "")).strip().lower()
        billing_url = reverse(
            "portal:client-order-panel-billing",
            kwargs={
                "customer_public_id": customer_public_id,
                "order_public_id": order_public_id,
            },
        )

        if status == "cancel":
            messages.info(request, "Paiement annulé. Vous pouvez réessayer quand vous voulez.")
            return HttpResponseRedirect(billing_url)

        paypal_token = str(request.GET.get("token", "")).strip()
        session_id = str(request.GET.get("session_id", "")).strip()
        payment_public_id = str(request.GET.get("payment", "")).strip() or None

        try:
            if session_id and session_id != "{CHECKOUT_SESSION_ID}":
                _order, payment, _invoice = billing_service.confirm_capture(
                    order_public_id=order.public_id,
                    provider_payment_id=session_id,
                    payment_public_id=payment_public_id,
                    actor=request.user,
                    source="client_portal_return",
                )
            elif paypal_token:
                _order, payment, _invoice = billing_service.confirm_capture(
                    order_public_id=order.public_id,
                    paypal_order_id=paypal_token,
                    payment_public_id=payment_public_id,
                    actor=request.user,
                    source="client_portal_return",
                )
            else:
                messages.warning(
                    request,
                    "Retour de paiement incomplet. "
                    "Si le débit a été effectué, contactez le support.",
                )
                return HttpResponseRedirect(billing_url)
        except DjangoValidationError as error:
            message = "; ".join(error.messages) if hasattr(error, "messages") else str(error)
            messages.error(request, message)
            response = HttpResponseRedirect(billing_url)
            return with_toast(response, message=message, variant="error")

        if payment is None:
            raise Http404
        if payment.status == Payment.Status.CAPTURED:
            messages.success(request, "Paiement confirmé. Votre facture est disponible.")
        else:
            messages.info(request, "Paiement en cours de confirmation.")
        return HttpResponseRedirect(billing_url)


def can_pay_online(customer: Customer) -> bool:
    method = customer.preferred_settlement_method
    if method == Customer.PreferredSettlementMethod.WIRE_TRANSFER:
        return False
    if method == Customer.PreferredSettlementMethod.STRIPE:
        return bool(settings.STRIPE_SECRET_KEY)
    if method == Customer.PreferredSettlementMethod.PAYPAL:
        return bool(settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET)
    return bool(
        (settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET) or settings.STRIPE_SECRET_KEY
    )


def default_online_provider(customer: Customer) -> str:
    method = customer.preferred_settlement_method
    if method == Customer.PreferredSettlementMethod.STRIPE:
        return Payment.Provider.STRIPE
    if method == Customer.PreferredSettlementMethod.PAYPAL:
        return Payment.Provider.PAYPAL
    if settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET:
        return Payment.Provider.PAYPAL
    return Payment.Provider.STRIPE
