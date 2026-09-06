from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.order_status_presentation import is_pickup_order
from apps.portal.shipping_forms import build_shipment_form_data, build_shipment_payload
from apps.portal.views_common import (
    badge_tone_for_status,
    production_workflow_service,
    shipment_service,
    status_label,
)
from apps.portal.views_staff import StaffOrderContextMixin
from apps.production.models import ProductionJob
from apps.shipping.services.methods import ShippingMethodService
from apps.shipping.views import build_label_download_response


class StaffOrderPanelShippingView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/shipping.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _form_data(self, request):
        return build_shipment_form_data(
            order=self.order,
            submitted_data=request.POST if request.method == "POST" else None,
        )

    def _shipment_for_panel(self, request):
        """Return shipment data only for carrier-delivered orders.

        A workshop pickup has no Sendcloud shipment by design.  Keeping that
        distinction at the view boundary also makes stale HTMX requests safe.
        """
        if is_pickup_order(self.order):
            return None
        _order, shipment = shipment_service.get_staff_shipment(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        return shipment

    def _panel_context(self, request, *, shipment, form_error: str = ""):
        try:
            production_job = self.order.production_job
        except ProductionJob.DoesNotExist:
            production_job = None
        shipping_method = (
            None
            if is_pickup_order(self.order)
            else ShippingMethodService().get_active_by_code(self.order.shipping_method_code)
        )
        return {
            "order": self.order,
            "shipment": shipment,
            "production_job": production_job,
            "shipping_ready": bool(
                production_job and production_job.status == ProductionJob.Status.READY_TO_SHIP
            ),
            "is_pickup": is_pickup_order(self.order),
            "can_confirm_pickup": request.user.has_perm("production.transition_productionjob"),
            "delivery_eta_label": shipping_method.eta_label if shipping_method else "",
            "can_create_shipment": request.user.has_perm("shipping.create_shipment"),
            "form_data": self._form_data(request),
            "form_error": form_error,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        shipment = self._shipment_for_panel(request)
        return render(request, self.template_name, self._panel_context(request, shipment=shipment))

    def post(self, request, order_public_id):
        if request.POST.get("action") == "confirm_pickup":
            if not request.user.has_perm("production.transition_productionjob"):
                raise PermissionDenied
            if not is_pickup_order(self.order):
                raise Http404

            form_error = ""
            try:
                production_workflow_service.transition_job(
                    order_public_id=self.order.public_id,
                    to_status=ProductionJob.Status.COMPLETED,
                    actor=request.user,
                    reason=request.POST.get("pickup_note", ""),
                    source="staff_portal_pickup_confirmation",
                )
            except ValidationError as exc:
                form_error = "; ".join(exc.messages)

            self.order.refresh_from_db()
            shipment = self._shipment_for_panel(request)
            response = render(
                request,
                self.template_name,
                self._panel_context(request, shipment=shipment, form_error=form_error),
            )
            if form_error:
                return with_toast(response, form_error, "error")
            return with_toast(response, "Retrait confirmé et OF terminé.", "success")

        if is_pickup_order(self.order):
            message = "Le retrait atelier se confirme avec « Confirmer le retrait »."
            response = render(
                request,
                self.template_name,
                self._panel_context(request, shipment=None, form_error=message),
            )
            return with_toast(response, message, "error")

        if not request.user.has_perm("shipping.create_shipment"):
            raise PermissionDenied

        form_error = ""
        try:
            _order, shipment = shipment_service.create_shipment(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
                payload=build_shipment_payload(request.POST),
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
        return with_toast(response, "Commande declaree dans Sendcloud.", "success")


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
            response = render(
                request,
                self.template_name,
                panel._panel_context(
                    request, shipment=shipment, form_error="; ".join(exc.messages)
                ),
            )
            return with_toast(response, "; ".join(exc.messages), "error")

        if _order is None or shipment is None:
            raise Http404
        response = render(
            request,
            self.template_name,
            panel._panel_context(request, shipment=shipment),
        )
        return with_toast(response, "Suivi Sendcloud actualise.", "success")


class StaffOrderShipmentLabelDownloadView(StaffOrderContextMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("shipping.view_shipment"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        _order, shipment = shipment_service.download_staff_shipment_label(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        if shipment is None:
            raise Http404
        return build_label_download_response(shipment)
