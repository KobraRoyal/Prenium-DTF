from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.portal.htmx import with_toast
from apps.portal.shipping_forms import build_shipment_form_data, build_shipment_payload
from apps.portal.views_common import (
    StaffPortalMixin,
    access_scope_service,
    badge_tone_for_status,
    production_workflow_service,
    shipment_service,
    status_label,
)
from apps.production.services.operations import AtelierOperationsService

atelier_operations_service = AtelierOperationsService()


class StaffAtelierOperationsPermissionMixin(StaffPortalMixin):
    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
        "production.scan_productionjob",
    )
    rejection_action = "production.operator_console_permission_rejected"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (
            not access_scope_service.can_access_staff_portal(request.user)
            or any(
                not request.user.has_perm(permission)
                for permission in self.required_permissions
            )
        ):
            record_event(
                action=self.rejection_action,
                actor=request.user,
                status=AuditLogEntry.Status.FAILURE,
                message="Accès à la console Atelier refusé.",
                metadata={"source": "staff_operations", "reason": "permission_denied"},
            )
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StaffAtelierOperationsContextMixin(StaffAtelierOperationsPermissionMixin):
    workspace_template_name = "portal/staff/operations/_workspace.html"

    def _filter_value(self, request, key: str, default: str = "") -> str:
        if request.method == "POST":
            return request.POST.get(key, default)
        return request.GET.get(key, default)

    def _workspace_context(
        self,
        request,
        *,
        feedback: str = "",
        feedback_tone: str = "success",
        shipment_error_order_public_id: str = "",
    ) -> dict[str, object]:
        can_view_shipping = request.user.has_perm("shipping.view_shipment")
        can_create_shipment = bool(
            can_view_shipping and request.user.has_perm("shipping.create_shipment")
        )
        workspace = atelier_operations_service.build_workspace(
            queue=self._filter_value(request, "queue", "active"),
            query=self._filter_value(request, "q", ""),
            page_number=self._filter_value(request, "page", "1"),
            include_shipping=can_view_shipping,
        )
        submitted_order_public_id = str(shipment_error_order_public_id or "")
        for row in workspace["rows"]:
            row["shipment_form_open"] = submitted_order_public_id == str(
                row["order"].public_id
            )
            if row["needs_shipping"] and can_create_shipment:
                submitted_data = None
                if submitted_order_public_id == str(row["order"].public_id):
                    submitted_data = request.POST
                row["shipment_form_data"] = build_shipment_form_data(
                    order=row["order"],
                    submitted_data=submitted_data,
                )
        return {
            **workspace,
            "can_transition": bool(
                request.user.has_perm("production.transition_productionjob")
                and request.user.has_perm("production.scan_transition_productionjob")
            ),
            "can_view_shipping": can_view_shipping,
            "can_create_shipment": can_create_shipment,
            "feedback": feedback,
            "feedback_tone": feedback_tone,
            "shipment_error_order_public_id": submitted_order_public_id,
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def _render_workspace(self, request, **kwargs):
        return render(
            request,
            self.workspace_template_name,
            self._workspace_context(request, **kwargs),
        )


class StaffAtelierOperationsView(StaffAtelierOperationsContextMixin, View):
    template_name = "portal/staff/operations/index.html"

    def get(self, request):
        context = self._workspace_context(request)
        if request.headers.get("HX-Request") == "true":
            return render(request, self.workspace_template_name, context)
        return render(
            request,
            self.template_name,
            {
                **context,
                "nav_mode": "staff",
                "nav_key": "staff-operations",
            },
        )


class StaffAtelierOperationTransitionView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "production.transition_productionjob",
        "production.scan_transition_productionjob",
    )

    def post(self, request, order_public_id):
        target_status = request.POST.get("to_status", "")
        try:
            _order, job, _transition = production_workflow_service.transition_job(
                order_public_id=order_public_id,
                to_status=target_status,
                actor=request.user,
                reason=request.POST.get("reason", ""),
                source="staff_operations",
            )
        except ValidationError as exc:
            message = "; ".join(exc.messages)
            response = self._render_workspace(
                request,
                feedback=message,
                feedback_tone="error",
            )
            return with_toast(response, message, "error")
        if job is None:
            raise Http404
        label = production_workflow_service.document_status_labels.get(job.status, job.status)
        message = f"{job.manufacturing_order_number} · statut « {label} » enregistré."
        response = self._render_workspace(request, feedback=message)
        return with_toast(response, message, "success")


class StaffAtelierOperationShipmentCreateView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "shipping.view_shipment",
        "shipping.create_shipment",
    )
    rejection_action = "shipping.operator_console_permission_rejected"

    def post(self, request, order_public_id):
        try:
            _order, shipment = shipment_service.create_shipment(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_operations",
                payload=build_shipment_payload(request.POST),
            )
        except ValidationError as exc:
            message = "; ".join(exc.messages)
            response = self._render_workspace(
                request,
                feedback=message,
                feedback_tone="error",
                shipment_error_order_public_id=str(order_public_id),
            )
            return with_toast(response, message, "error")
        if shipment is None:
            raise Http404
        message = "Commande déclarée dans Sendcloud."
        response = self._render_workspace(request, feedback=message)
        return with_toast(response, message, "success")


class StaffAtelierOperationShipmentSyncView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "shipping.view_shipment",
    )
    rejection_action = "shipping.operator_console_permission_rejected"

    def post(self, request, order_public_id):
        try:
            _order, shipment = shipment_service.sync_shipment_tracking_from_sendcloud(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_operations",
            )
        except ValidationError as exc:
            message = "; ".join(exc.messages)
            response = self._render_workspace(
                request,
                feedback=message,
                feedback_tone="error",
            )
            return with_toast(response, message, "error")
        if shipment is None:
            raise Http404
        message = "Suivi Sendcloud actualisé."
        response = self._render_workspace(request, feedback=message)
        return with_toast(response, message, "success")
