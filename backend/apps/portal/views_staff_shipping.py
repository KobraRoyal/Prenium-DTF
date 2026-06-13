from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.views_common import badge_tone_for_status, shipment_service, status_label
from apps.portal.views_staff import StaffOrderContextMixin


class StaffOrderPanelShippingView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/shipping.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        _order, shipment = shipment_service.get_staff_shipment(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "shipment": shipment,
                "form_error": "",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
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
            {
                "order": self.order,
                "shipment": shipment,
                "form_error": form_error,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
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
                {
                    "order": self.order,
                    "shipment": shipment,
                    "form_error": form_error,
                    "badge_tone_for_status": badge_tone_for_status,
                    "status_label": status_label,
                },
            )
            return with_toast(response, form_error, "error")

        if _order is None or shipment is None:
            raise Http404

        response = render(
            request,
            self.template_name,
            {
                "order": self.order,
                "shipment": shipment,
                "form_error": "",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
        return with_toast(response, "Suivi Sendcloud actualise.", "success")
