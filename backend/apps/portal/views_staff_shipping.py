from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import badge_tone_for_status, shipment_service, status_label
from apps.portal.views_staff import StaffOrderContextMixin
from apps.production.models import ProductionJob


class StaffOrderPanelShippingView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/shipping.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _form_data(self, request):
        customer = self.order.customer
        if request.method == "POST":
            return {
                key: request.POST.get(key, "")
                for key in (
                    "shipping_option_code",
                    "contract_id",
                    "recipient_name",
                    "recipient_company_name",
                    "recipient_email",
                    "recipient_phone_number",
                    "recipient_country_code",
                    "recipient_city",
                    "recipient_postal_code",
                    "recipient_address_line_1",
                    "recipient_address_line_2",
                    "recipient_house_number",
                    "parcel_weight_value",
                )
            }
        return {
            "shipping_option_code": "",
            "contract_id": "",
            "recipient_name": customer.name,
            "recipient_company_name": customer.name,
            "recipient_email": customer.billing_email,
            "recipient_phone_number": "",
            "recipient_country_code": customer.shipping_country or "FR",
            "recipient_city": customer.shipping_city,
            "recipient_postal_code": customer.shipping_postal_code,
            "recipient_address_line_1": customer.shipping_address_line1,
            "recipient_address_line_2": customer.shipping_address_line2,
            "recipient_house_number": "",
            "parcel_weight_value": "1.0",
        }

    def _panel_context(self, request, *, shipment, form_error: str = ""):
        try:
            production_job = self.order.production_job
        except ProductionJob.DoesNotExist:
            production_job = None
        return {
            "order": self.order,
            "shipment": shipment,
            "production_job": production_job,
            "shipping_ready": bool(
                production_job
                and production_job.status == ProductionJob.Status.READY_TO_SHIP
            ),
            "can_create_shipment": request.user.has_perm("shipping.create_shipment"),
            "form_data": self._form_data(request),
            "form_error": form_error,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        _order, shipment = shipment_service.get_staff_shipment(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        return render(
            request,
            self.template_name,
            self._panel_context(request, shipment=shipment),
        )

    def post(self, request, order_public_id):
        if not request.user.has_perm("shipping.create_shipment"):
            raise PermissionDenied

        payload = {
            "shipping_option_code": request.POST.get("shipping_option_code", ""),
            "contract_id": request.POST.get("contract_id") or None,
            "recipient": {
                "name": request.POST.get("recipient_name", ""),
                "address_line_1": request.POST.get("recipient_address_line_1", ""),
                "house_number": request.POST.get("recipient_house_number", ""),
                "postal_code": request.POST.get("recipient_postal_code", ""),
                "city": request.POST.get("recipient_city", ""),
                "country_code": request.POST.get("recipient_country_code", ""),
                "email": request.POST.get("recipient_email", ""),
                "company_name": request.POST.get("recipient_company_name", ""),
                "address_line_2": request.POST.get("recipient_address_line_2", ""),
                "phone_number": request.POST.get("recipient_phone_number", ""),
            },
            "parcel": {
                "weight": {
                    "value": request.POST.get("parcel_weight_value", ""),
                    "unit": "kg",
                }
            },
            "label_details": {"mime_type": "application/pdf", "dpi": 72},
        }
        form_error = ""
        try:
            _order, shipment = shipment_service.create_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
                payload=payload,
            )
        except ValidationError as exc:
            _order, shipment = shipment_service.get_staff_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
            form_error = "; ".join(exc.messages)

        response = render(
            request,
            self.template_name,
            self._panel_context(request, shipment=shipment, form_error=form_error),
        )
        if form_error:
            return with_toast(response, form_error, "error")
        return with_toast(response, "Expedition creee.", "success")


class StaffOrderPanelShippingSyncView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/shipping.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, order_public_id):
        panel = StaffOrderPanelShippingView()
        panel.order = self.order
        try:
            _order, shipment = shipment_service.sync_shipment_tracking_from_sendcloud(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
        except ValidationError as exc:
            _order, shipment = shipment_service.get_staff_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
            form_error = "; ".join(exc.messages)
            response = render(
                request,
                self.template_name,
                panel._panel_context(request, shipment=shipment, form_error=form_error),
            )
            return with_toast(response, form_error, "error")

        if _order is None or shipment is None:
            raise Http404

        response = render(
            request,
            self.template_name,
            panel._panel_context(request, shipment=shipment),
        )
        return with_toast(response, "Suivi Sendcloud actualise.", "success")
