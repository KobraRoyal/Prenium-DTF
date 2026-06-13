from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.billing.models import Invoice
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    badge_tone_for_status,
    billing_service,
    htmx_target_id,
    invoice_domain_service,
    meterage_context_for_order,
    staff_order_upload_rows,
    status_label,
    upload_service,
)
from apps.portal.views_staff import StaffOrderContextMixin


class StaffOrderPanelBillingView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/billing.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("billing.view_payment"):
            raise PermissionDenied
        if not request.user.has_perm("billing.view_invoice"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _billing_context(self, request):
        _order, payment, invoice = billing_service.get_staff_billing(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        upload_rows = staff_order_upload_rows(self.order)
        customer = self.order.customer
        can_mark_invoice_paid = (
            request.user.has_perm("billing.mark_invoice_paid")
            and invoice is not None
            and invoice.paid_at is None
            and customer.preferred_settlement_method == "wire_transfer"
        )
        return {
            "order": self.order,
            "payment": payment,
            "invoice": invoice,
            "upload_rows": upload_rows,
            "can_mark_invoice_paid": can_mark_invoice_paid,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        return render(
            request,
            self.template_name,
            self._billing_context(request),
        )

    def post(self, request, order_public_id):
        if not request.user.has_perm("orders.change_order"):
            raise PermissionDenied
        raw = request.POST.get("order_meterage_override_linear_m", "")
        tid = htmx_target_id(request)
        slot_partial = tid.startswith("staff-order-meterage-slot")
        try:
            upload_service.set_staff_order_meterage_linear_override(
                order=self.order,
                actor=request.user,
                raw_value=raw,
            )
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            ctx = self._meterage_partial_context(request, form_error=msg, hx_target_id=tid)
            tpl = (
                "components/portal/staff_meterage_section.html"
                if slot_partial
                else self.template_name
            )
            response = render(request, tpl, ctx)
            return with_toast(response, msg, "error")
        self.order.refresh_from_db()
        ctx = self._meterage_partial_context(request, form_error="", hx_target_id=tid)
        if slot_partial:
            response = render(request, "components/portal/staff_meterage_section.html", ctx)
        else:
            response = render(request, self.template_name, self._billing_context(request))
        return with_toast(response, "Métrage linéaire commande enregistré.", "success")

    def _meterage_partial_context(self, request, *, form_error: str, hx_target_id: str):
        """Contexte pour le fragment métrage (HTMX) : cible du formulaire
        selon l’onglet d’origine.
        """
        base = meterage_context_for_order(request, self.order, form_error)
        if hx_target_id and hx_target_id.startswith("staff-order-meterage-slot"):
            base["meterage_hx_target"] = f"#{hx_target_id}"
        else:
            base["meterage_hx_target"] = "#staff-order-panel"
        return {**self._billing_context(request), **base}


class StaffInvoiceMarkPaidView(StaffOrderContextMixin, View):
    """Marque la facture de la commande comme payée (virement reçu)."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("billing.view_invoice"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, order_public_id):
        if not request.user.has_perm("billing.mark_invoice_paid"):
            raise PermissionDenied
        invoice = Invoice.objects.filter(order=self.order).first()
        if invoice is None:
            raise Http404
        panel = StaffOrderPanelBillingView()
        panel.order = self.order
        try:
            invoice_domain_service.mark_invoice_paid_by_staff(
                invoice=invoice,
                actor=request.user,
                source="staff_portal.billing",
            )
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            response = render(request, panel.template_name, panel._billing_context(request))
            return with_toast(response, msg, "error")
        response = render(request, panel.template_name, panel._billing_context(request))
        return with_toast(response, "Facture marquée comme payée (virement reçu).", "success")
