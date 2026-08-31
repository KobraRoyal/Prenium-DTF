from __future__ import annotations

from uuid import UUID

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.b2b_order_projects.permissions import b2b_order_projects_enabled_for_customer
from apps.portal.htmx import with_toast
from apps.portal.views_checkout import checkout_choice_context
from apps.portal.views_common import (
    ScopedCustomerMixin,
    badge_tone_for_status,
    order_service,
    status_label,
    upload_service,
)


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
                **checkout_choice_context(customer=self.customer, order=order),
            },
        )
