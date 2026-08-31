from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
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


def _wants_json_response(request) -> bool:
    accept = str(request.headers.get("Accept", "")).lower()
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in accept
    )


def _popup_return_requested(request) -> bool:
    if request.method == "POST":
        return str(request.POST.get("popup", "")).strip() == "1"
    return str(request.GET.get("popup", "")).strip() == "1"


def _sdk_flow_requested(request) -> bool:
    if request.method == "POST":
        return str(request.POST.get("sdk", "")).strip() == "1"
    return False


def _append_query_param(url: str, key: str, value: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{key}={value}"


def _render_payment_popup_return(
    request,
    *,
    popup_status: str,
    fallback_url: str,
    popup_message: str = "",
):
    return render(
        request,
        "portal/client/payment_return_popup.html",
        {
            "popup_status": popup_status,
            "popup_message": popup_message,
            "fallback_url": fallback_url,
        },
    )


def client_order_billing_landing_url(
    *,
    customer_public_id,
    order_public_id,
    paid: bool = False,
    cancelled: bool = False,
    pay: bool = False,
    checkout_success: bool = False,
) -> str:
    """URL fiche commande complète (shell) avec onglet règlement.

    Les endpoints ``panels/billing/`` sont des partiels HTMX : un redirect
    provider ne doit jamais y aboutir en navigation pleine page.
    """
    path = reverse(
        "portal:client-order-detail",
        kwargs={
            "customer_public_id": customer_public_id,
            "order_public_id": order_public_id,
        },
    )
    params: list[str] = ["panel=billing"]
    if paid:
        params.append("paid=1")
    if cancelled:
        params.append("cancelled=1")
    if pay:
        params.append("pay=1")
    if checkout_success:
        params.append("checkout=success")
    return f"{path}?{'&'.join(params)}"


def redirect_full_page_billing_panel_to_shell(
    request,
    *,
    customer_public_id,
    order_public_id,
):
    """Si navigation pleine page, renvoyer vers la fiche shell (pas le partiel HTMX)."""
    if request.headers.get("HX-Request"):
        return None
    return HttpResponseRedirect(
        client_order_billing_landing_url(
            customer_public_id=customer_public_id,
            order_public_id=order_public_id,
            paid=str(request.GET.get("paid", "")).strip() == "1",
            cancelled=str(request.GET.get("cancelled", "")).strip() == "1",
            pay=str(request.GET.get("pay", "")).strip() == "1",
            checkout_success=str(request.GET.get("checkout", "")).strip() == "success",
        )
    )


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
        available_ids = {item["id"] for item in available_payment_providers()}
        billing_url = client_order_billing_landing_url(
            customer_public_id=customer_public_id,
            order_public_id=order_public_id,
            pay=True,
        )
        if not available_ids:
            messages.error(request, "Aucun moyen de paiement en ligne n'est configuré.")
            return HttpResponseRedirect(billing_url)
        if provider and provider not in available_ids:
            messages.error(request, "Moyen de paiement non disponible.")
            return HttpResponseRedirect(billing_url)
        if not provider:
            if len(available_ids) == 1:
                provider = next(iter(available_ids))
            else:
                message = "Choisissez un moyen de paiement."
                if _wants_json_response(request):
                    return JsonResponse({"ok": False, "error": message}, status=400)
                messages.error(request, message)
                return HttpResponseRedirect(billing_url)
        popup_requested = _popup_return_requested(request) and provider == Payment.Provider.PAYPAL
        success_path = reverse(
            "portal:client-order-payment-return",
            kwargs={
                "customer_public_id": customer_public_id,
                "order_public_id": order_public_id,
            },
        )
        # Stripe Checkout remplace {{CHECKOUT_SESSION_ID}} ; PayPal refuse `{` `}` dans return_url.
        if provider == Payment.Provider.STRIPE:
            success_url = _absolute_portal_url(
                f"{success_path}?status=success&session_id={{CHECKOUT_SESSION_ID}}"
            )
        else:
            success_url = _absolute_portal_url(f"{success_path}?status=success")
        cancel_url = _absolute_portal_url(f"{success_path}?status=cancel&provider={provider}")
        if popup_requested:
            success_url = _append_query_param(success_url, "popup", "1")
            cancel_url = _append_query_param(cancel_url, "popup", "1")

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
            if _wants_json_response(request):
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            response = HttpResponseRedirect(billing_url)
            return with_toast(response, message=message, variant="error")

        if payment is None or not payment.approval_url:
            raise Http404
        if _wants_json_response(request):
            payload: dict[str, str | bool] = {
                "ok": True,
                "provider": payment.provider,
            }
            if payment.provider == Payment.Provider.PAYPAL and _sdk_flow_requested(request):
                if not payment.paypal_order_id:
                    return JsonResponse(
                        {
                            "ok": False,
                            "error": "Identifiant PayPal indisponible.",
                        },
                        status=500,
                    )
                payload["paypal_order_id"] = payment.paypal_order_id
            else:
                payload["approval_url"] = payment.approval_url
            return JsonResponse(payload)
        return HttpResponseRedirect(payment.approval_url)


class ClientOrderPaymentCaptureView(ClientOwnerRequiredMixin, _ClientOrderLookupMixin, View):
    """Capture PayPal après approbation via le SDK JavaScript (Smart Buttons)."""

    def post(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        paypal_order_id = str(request.POST.get("paypal_order_id", "")).strip()
        billing_url = client_order_billing_landing_url(
            customer_public_id=customer_public_id,
            order_public_id=order_public_id,
            pay=True,
        )
        if not paypal_order_id:
            message = "Identifiant PayPal manquant."
            if _wants_json_response(request):
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            return HttpResponseRedirect(billing_url)

        try:
            _order, payment, _invoice = billing_service.confirm_capture(
                order_public_id=order.public_id,
                paypal_order_id=paypal_order_id,
                expected_provider=Payment.Provider.PAYPAL,
                actor=request.user,
                source="client_portal_sdk",
            )
        except DjangoValidationError as error:
            message = "; ".join(error.messages) if hasattr(error, "messages") else str(error)
            if _wants_json_response(request):
                return JsonResponse({"ok": False, "error": message}, status=400)
            messages.error(request, message)
            response = HttpResponseRedirect(billing_url)
            return with_toast(response, message=message, variant="error")

        if payment is None:
            raise Http404
        if payment.status == Payment.Status.CAPTURED:
            redirect_url = client_order_billing_landing_url(
                customer_public_id=customer_public_id,
                order_public_id=order_public_id,
                paid=True,
            )
            if _wants_json_response(request):
                return JsonResponse(
                    {
                        "ok": True,
                        "status": "captured",
                        "redirect_url": redirect_url,
                    }
                )
            messages.success(
                request,
                "Paiement confirmé. Votre justificatif de paiement est disponible.",
            )
            return HttpResponseRedirect(redirect_url)

        message = "Paiement en cours de confirmation."
        if _wants_json_response(request):
            return JsonResponse({"ok": False, "error": message}, status=409)
        messages.info(request, message)
        return HttpResponseRedirect(billing_url)


class ClientOrderPaymentReturnView(ClientOwnerRequiredMixin, _ClientOrderLookupMixin, View):
    """Retour provider : capture/confirm + redirection fiche commande (onglet règlement)."""

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        status = str(request.GET.get("status", "")).strip().lower()
        billing_url = client_order_billing_landing_url(
            customer_public_id=customer_public_id,
            order_public_id=order_public_id,
        )
        popup_return = _popup_return_requested(request)
        paypal_token = str(request.GET.get("token", "")).strip()
        session_id = str(request.GET.get("session_id", "")).strip()
        payment_public_id = str(request.GET.get("payment", "")).strip() or None

        if status == "cancel":
            requested_provider = ""
            if paypal_token:
                requested_provider = Payment.Provider.PAYPAL
            elif session_id:
                requested_provider = Payment.Provider.STRIPE
            provider_payment_id = paypal_token or session_id
            if requested_provider and provider_payment_id:
                billing_service.cancel_open_payment_for_order(
                    order_public_id=order.public_id,
                    provider=requested_provider,
                    provider_payment_id=provider_payment_id,
                    actor=request.user,
                    source="client_portal_return",
                )
            fallback_url = client_order_billing_landing_url(
                customer_public_id=customer_public_id,
                order_public_id=order_public_id,
                cancelled=True,
                pay=True,
            )
            if popup_return:
                return _render_payment_popup_return(
                    request,
                    popup_status="cancel",
                    fallback_url=fallback_url,
                )
            messages.info(request, "Paiement non validé. Vous pouvez reprendre le règlement.")
            return HttpResponseRedirect(fallback_url)

        try:
            if session_id and session_id != "{CHECKOUT_SESSION_ID}":
                _order, payment, _invoice = billing_service.confirm_capture(
                    order_public_id=order.public_id,
                    provider_payment_id=session_id,
                    payment_public_id=payment_public_id,
                    expected_provider=Payment.Provider.STRIPE,
                    actor=request.user,
                    source="client_portal_return",
                )
            elif paypal_token:
                _order, payment, _invoice = billing_service.confirm_capture(
                    order_public_id=order.public_id,
                    paypal_order_id=paypal_token,
                    payment_public_id=payment_public_id,
                    expected_provider=Payment.Provider.PAYPAL,
                    actor=request.user,
                    source="client_portal_return",
                )
            else:
                message = (
                    "Retour de paiement incomplet. "
                    "Si le débit a été effectué, contactez le support."
                )
                if popup_return:
                    return _render_payment_popup_return(
                        request,
                        popup_status="error",
                        popup_message=message,
                        fallback_url=billing_url,
                    )
                messages.warning(request, message)
                return HttpResponseRedirect(billing_url)
        except DjangoValidationError as error:
            message = "; ".join(error.messages) if hasattr(error, "messages") else str(error)
            if popup_return:
                return _render_payment_popup_return(
                    request,
                    popup_status="error",
                    popup_message=message,
                    fallback_url=billing_url,
                )
            messages.error(request, message)
            response = HttpResponseRedirect(billing_url)
            return with_toast(response, message=message, variant="error")

        if payment is None:
            raise Http404
        if payment.status == Payment.Status.CAPTURED:
            fallback_url = client_order_billing_landing_url(
                customer_public_id=customer_public_id,
                order_public_id=order_public_id,
                paid=True,
            )
            if popup_return:
                return _render_payment_popup_return(
                    request,
                    popup_status="success",
                    fallback_url=fallback_url,
                )
            messages.success(
                request,
                "Paiement confirmé. Votre justificatif de paiement est disponible.",
            )
            return HttpResponseRedirect(fallback_url)
        if popup_return:
            return _render_payment_popup_return(
                request,
                popup_status="error",
                popup_message="Paiement en cours de confirmation.",
                fallback_url=billing_url,
            )
        messages.info(request, "Paiement en cours de confirmation.")
        return HttpResponseRedirect(billing_url)


def available_payment_providers() -> list[dict[str, str]]:
    """Options de paiement proposées au client, selon la config projet."""
    from apps.billing.services.gateways import configured_online_providers

    labels = {
        Payment.Provider.PAYPAL: "PayPal",
        Payment.Provider.STRIPE: "Carte bancaire",
    }
    return [
        {"id": provider, "label": labels.get(provider, provider)}
        for provider in configured_online_providers()
    ]


def can_pay_online(customer: Customer | None = None) -> bool:
    """Paiement en ligne possible si au moins un provider est installé."""
    _ = customer  # conservé pour compatibilité d’appel
    return bool(available_payment_providers())


def default_online_provider(customer: Customer) -> str:
    providers = [item["id"] for item in available_payment_providers()]
    if not providers:
        return ""
    preferred = customer.preferred_settlement_method
    if preferred in providers:
        return preferred
    return providers[0]


def paypal_sdk_context(*, order, payment_providers: list[dict[str, str]]) -> dict[str, object]:
    """Config front PayPal JS SDK (Smart Buttons) pour la modale client."""
    has_paypal = any(item["id"] == Payment.Provider.PAYPAL for item in payment_providers)
    client_id = settings.PAYPAL_CLIENT_ID if has_paypal else ""
    if not client_id:
        return {
            "paypal_sdk_enabled": False,
            "paypal_client_id": "",
            "paypal_sdk_currency": "",
        }
    return {
        "paypal_sdk_enabled": True,
        "paypal_client_id": client_id,
        "paypal_sdk_currency": str(order.currency or "EUR").upper(),
    }
