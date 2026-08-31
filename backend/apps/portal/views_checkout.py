"""Checkout client historique (upload synchrone + facturation différée).

Conservé pour les comptes sans projets B2B asynchrones. Lorsque
`b2b_order_projects_enabled_for_customer` est vrai, `/checkout/` redirige vers
la création de projet (`client_new_order_url`) — deux parcours documentés, un
seul actif par compte.
"""

from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.b2b_order_projects.permissions import (
    b2b_order_projects_enabled_for_customer,
    client_new_order_url,
)
from apps.portal.views_common import (
    ScopedCustomerMixin,
    badge_tone_for_status,
    order_service,
    status_label,
    upload_service,
)


def checkout_choice_context(*, customer, order):
    from apps.processing_time.services.options import ProcessingTimeOptionService
    from apps.shipping.services.methods import ShippingMethodService

    return {
        **ShippingMethodService().checkout_ui_context(
            customer=customer,
            order=order,
            widget="radios",
        ),
        **ProcessingTimeOptionService().checkout_ui_context(
            customer=customer,
            order=order,
            widget="radios",
        ),
    }


class ClientCheckoutView(ScopedCustomerMixin, View):
    template_name = "portal/client/checkout.html"

    def get(self, request, customer_public_id):
        if b2b_order_projects_enabled_for_customer(self.customer):
            return HttpResponseRedirect(self._asynchronous_order_url())
        return render(
            request,
            self.template_name,
            self._build_context(request=request),
        )

    def post(self, request, customer_public_id):
        if b2b_order_projects_enabled_for_customer(self.customer):
            return HttpResponseRedirect(self._asynchronous_order_url())
        customer_note = request.POST.get("customer_note", "").strip()

        try:
            order = order_service.create_b2b_deferred_order(
                customer=self.customer,
                actor=request.user,
                customer_membership=self.customer_membership,
                customer_note=customer_note,
                source="client_checkout",
            )
        except ValidationError as exc:
            context = self._build_context(
                request=request,
                creation_error="; ".join(exc.messages),
            )
            return render(request, self.template_name, context, status=400)

        checkout_url = reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": self.customer.public_id},
        )
        return HttpResponseRedirect(f"{checkout_url}?order={order.public_id}")

    def _asynchronous_order_url(self):
        return client_new_order_url(customer=self.customer)

    def _resolve_order(self, request):
        raw_order_public_id = str(request.GET.get("order", "")).strip()
        if not raw_order_public_id:
            return None
        try:
            order_public_id = UUID(raw_order_public_id)
        except ValueError:
            return None
        return order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )

    def _checkout_choice_context(self, *, order):
        return checkout_choice_context(customer=self.customer, order=order)

    def _build_context(self, *, request, creation_error: str = ""):
        order = self._resolve_order(request)
        uploads = []
        if order is not None:
            _order, uploads_qs = upload_service.list_customer_order_uploads(
                customer=self.customer,
                order_public_id=order.public_id,
            )
            uploads = list(uploads_qs)
        return {
            "customer": self.customer,
            "selected_order": order,
            "uploads": uploads,
            "creation_error": creation_error,
            "submit_error": request.GET.get("submit_error", ""),
            "nav_mode": "client",
            "nav_key": "client-checkout",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
            **(self._checkout_choice_context(order=order) if order is not None else {}),
        }


class ClientCheckoutSubmitView(ScopedCustomerMixin, View):
    def post(self, request, customer_public_id):
        if b2b_order_projects_enabled_for_customer(self.customer):
            raise Http404
        raw_order_public_id = str(request.POST.get("order_public_id", "")).strip()
        try:
            order_public_id = UUID(raw_order_public_id)
        except ValueError as exc:
            raise Http404 from exc
        checkout_url = reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": self.customer.public_id},
        )
        if request.POST.get("confirm_checkout") != "on":
            query = f"{checkout_url}?order={order_public_id}&submit_error=confirm"
            return HttpResponseRedirect(query)

        try:
            order_service.submit_b2b_deferred_order(
                customer=self.customer,
                actor=request.user,
                customer_membership=self.customer_membership,
                order_public_id=order_public_id,
                source="client_checkout",
                billing_mode=str(
                    request.POST.get("billing_mode")
                    or getattr(self.customer, "default_billing_mode", "deferred")
                ).strip(),
                shipping_method_code=(request.POST.get("shipping_method_code") or "").strip()
                or None,
                processing_time_code=(request.POST.get("processing_time_code") or "").strip()
                or None,
            )
        except ValidationError:
            query = f"{checkout_url}?order={order_public_id}&submit_error=validation"
            return HttpResponseRedirect(query)

        detail_url = reverse(
            "portal:client-order-detail",
            kwargs={
                "customer_public_id": self.customer.public_id,
                "order_public_id": order_public_id,
            },
        )
        return HttpResponseRedirect(detail_url)
