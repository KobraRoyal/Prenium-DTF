from __future__ import annotations

from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.billing.models import Payment
from apps.portal.views_client import ClientOrderContextMixin
from apps.portal.views_common import ClientOwnerRequiredMixin, billing_service
from apps.portal.views_payments import (
    available_payment_providers,
    can_pay_online,
    default_online_provider,
    paypal_sdk_context,
    redirect_full_page_billing_panel_to_shell,
)


class ClientOrderPanelBillingView(ClientOwnerRequiredMixin, ClientOrderContextMixin, View):
    template_name = "portal/client/panels/billing.html"

    def get(self, request, customer_public_id, order_public_id):
        shell_redirect = redirect_full_page_billing_panel_to_shell(
            request,
            customer_public_id=customer_public_id,
            order_public_id=order_public_id,
        )
        if shell_redirect is not None:
            return shell_redirect

        order, payment, invoice = billing_service.get_customer_billing(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        settlement = order.customer.preferred_settlement_method
        providers = available_payment_providers()
        from apps.billing.services.production_payment_gate import order_awaits_client_payment

        awaits_payment = order_awaits_client_payment(order)
        show_pay_cta = (
            awaits_payment
            and invoice is None
            and can_pay_online(order.customer)
            and (
                payment is None
                or payment.status
                in {
                    Payment.Status.FAILED,
                    Payment.Status.CANCELLED,
                    Payment.Status.PENDING,
                    Payment.Status.APPROVED,
                }
            )
        )
        can_resume_online_payment = bool(
            payment is not None
            and payment.approval_url
            and payment.status
            not in {
                Payment.Status.CAPTURED,
                Payment.Status.CAPTURED_REVIEW,
            }
            and can_pay_online(order.customer)
        )
        return render(
            request,
            self.template_name,
            self.client_order_context(
                order=order,
                payment=payment,
                invoice=invoice,
                active_panel="billing",
                show_pay_cta=show_pay_cta,
                show_pay_dialog=show_pay_cta or can_resume_online_payment,
                awaits_client_payment=awaits_payment,
                payment_providers=providers,
                online_provider=default_online_provider(order.customer) if show_pay_cta else "",
                settlement_method=settlement,
                open_pay_dialog=(show_pay_cta or can_resume_online_payment)
                and str(request.GET.get("pay", "")).strip() == "1",
                **paypal_sdk_context(order=order, payment_providers=providers),
            ),
        )
