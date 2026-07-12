from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.b2b_order_projects.permissions import b2b_order_projects_enabled_for_customer
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    ScopedCustomerMixin,
    badge_tone_for_status,
    order_service,
    status_label,
    upload_service,
)


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
        return reverse(
            "portal:client-order-project-create",
            kwargs={"customer_public_id": self.customer.public_id},
        )

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
        }


class ClientCheckoutUploadPartialView(ScopedCustomerMixin, View):
    template_name = "portal/client/partials/checkout_uploads.html"

    def post(self, request, customer_public_id):
        self._reject_replaced_checkout()
        order_public_id = request.POST.get("order_public_id", "").strip()
        try:
            order_public_id = UUID(order_public_id)
        except ValueError as exc:
            raise Http404 from exc
        upload_error = ""
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404

        uploaded_file = request.FILES.get("file")
        if uploaded_file is None:
            upload_error = "Selectionnez un fichier avant envoi."
        else:
            try:
                raw_qty = request.POST.get("quantity", "1").strip()
                try:
                    qty = int(raw_qty) if raw_qty else 1
                except ValueError as exc:
                    raise ValidationError("Quantité invalide.") from exc
                upload_service.create_upload(
                    customer=self.customer,
                    actor=request.user,
                    uploaded_file=uploaded_file,
                    customer_membership=self.customer_membership,
                    order_public_id=order.public_id,
                    source="client_checkout",
                    quantity=qty,
                    support_color_hex=request.POST.get("support_color_hex", "").strip(),
                )
            except ValidationError as exc:
                upload_error = "; ".join(exc.messages)

        _order, uploads_qs = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        response = render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "uploads": list(uploads_qs),
                "upload_error": upload_error,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
            status=400 if upload_error else 200,
        )
        if upload_error:
            with_toast(response, upload_error, "error")
        else:
            response["HX-Trigger"] = "checkoutUploadsUpdated"
            with_toast(response, "Fichier ajoute.", "success")
        return response

    def _reject_replaced_checkout(self):
        if b2b_order_projects_enabled_for_customer(self.customer):
            raise Http404


class ClientCheckoutSummaryPartialView(ScopedCustomerMixin, View):
    template_name = "portal/client/partials/checkout_summary.html"

    def get(self, request, customer_public_id):
        if b2b_order_projects_enabled_for_customer(self.customer):
            raise Http404
        raw_order_public_id = str(request.GET.get("order", "")).strip()
        try:
            order_public_id = UUID(raw_order_public_id)
        except ValueError as exc:
            raise Http404 from exc
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        _order, uploads_qs = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "uploads": list(uploads_qs),
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


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
