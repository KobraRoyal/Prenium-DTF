from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.notifications.services.transactional import schedule_file_correction_requested_email
from apps.portal.htmx import with_toast
from apps.portal.services.atelier_operator_context import build_operator_context
from apps.portal.shipping_forms import build_shipment_form_data, build_shipment_payload
from apps.portal.views_common import (
    StaffPortalMixin,
    access_scope_service,
    badge_tone_for_status,
    order_service,
    production_workflow_service,
    shipment_service,
    status_label,
    upload_service,
)
from apps.production.services.machine_assignments import ProductionMachineAssignmentService
from apps.production.services.operations import AtelierOperationsService
from apps.production.services.print_tracking import ProductionPrintTrackingService
from apps.uploads.models import OrderUploadReview
from apps.uploads.services.reviews import OrderUploadReviewService, OrderUploadReviewTargetNotFound

atelier_operations_service = AtelierOperationsService()
review_service = OrderUploadReviewService()


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
                not request.user.has_perm(permission) for permission in self.required_permissions
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
        machine_error: str = "",
        print_error: str = "",
        meterage_error: str = "",
        inspection_error: str = "",
        inspection_error_upload_id: str = "",
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
            row["workflow_tabs"] = atelier_operations_service.workflow_panel_tabs(
                order=row["order"],
                focus_panel=row["focus_panel"],
                user=request.user,
            )
            row["shipment_form_open"] = submitted_order_public_id == str(row["order"].public_id)
            if row["needs_shipping"] and can_create_shipment:
                submitted_data = None
                if submitted_order_public_id == str(row["order"].public_id):
                    submitted_data = request.POST
                row["shipment_form_data"] = build_shipment_form_data(
                    order=row["order"],
                    submitted_data=submitted_data,
                )
        context = {
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
        focus_row = workspace.get("focus_row")
        if focus_row:
            context.update(
                build_operator_context(
                    request,
                    row=focus_row,
                    machine_error=machine_error,
                    print_error=print_error,
                    meterage_error=meterage_error,
                    inspection_error=inspection_error,
                    inspection_error_upload_id=inspection_error_upload_id,
                )
            )
            context["focus_row"] = focus_row
        return context

    def _render_workspace(self, request, **kwargs):
        return render(
            request,
            self.workspace_template_name,
            self._workspace_context(request, **kwargs),
        )

    def _staff_order(self, order_public_id):
        order = order_service.get_staff_order(order_public_id)
        if order is None:
            raise Http404
        return order


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


class StaffAtelierOperationUploadReviewView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "uploads.review_orderupload",
    )

    def post(self, request, order_public_id, upload_public_id):
        order = self._staff_order(order_public_id)
        try:
            review = review_service.review_upload(
                order=order,
                upload_public_id=upload_public_id,
                actor=request.user,
                status=request.POST.get("status", ""),
                reason_code=request.POST.get("reason_code", ""),
                comment=request.POST.get("comment", ""),
                source="staff_operations",
            )
        except OrderUploadReviewTargetNotFound as exc:
            raise Http404 from exc
        except ValidationError as exc:
            message = " ".join(getattr(exc, "messages", None) or [str(exc)])
            response = self._render_workspace(
                request,
                feedback=message,
                feedback_tone="error",
                inspection_error=message,
                inspection_error_upload_id=upload_public_id,
            )
            return with_toast(response, message, "error")

        if review.status == OrderUploadReview.Status.CHANGES_REQUESTED:
            schedule_file_correction_requested_email(review_public_id=review.public_id)
            message = "Correction enregistrée. Notification client mise en file d’envoi."
        else:
            message = "Fichier approuvé pour production."
        response = self._render_workspace(request, feedback=message)
        return with_toast(response, message, "success")


class StaffAtelierOperationMachineAssignView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "production.assign_productionmachine",
    )

    def post(self, request, order_public_id):
        machine_error = ""
        changed = False
        try:
            job, _assignment, changed = ProductionMachineAssignmentService().assign(
                order_public_id=order_public_id,
                machine_public_id=request.POST.get("machine_public_id", ""),
                actor=request.user,
                source="staff_operations",
                reason=request.POST.get("machine_reason", ""),
            )
        except ValidationError as exc:
            machine_error = "; ".join(exc.messages)
            job = production_workflow_service.get_or_create_for_order(
                order=self._staff_order(order_public_id)
            )
        if job is None:
            raise Http404
        if machine_error:
            response = self._render_workspace(request, machine_error=machine_error)
            return with_toast(response, machine_error, "error")
        message = (
            "Imprimante attribuée à l’OF." if changed else "Cette imprimante est déjà attribuée."
        )
        response = self._render_workspace(request, feedback=message)
        return with_toast(response, message, "success" if changed else "info")


class StaffAtelierOperationPrintConfirmView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "production.confirm_productionprint",
    )

    def post(self, request, order_public_id):
        print_error = ""
        created = False
        try:
            job, _print_record, created = ProductionPrintTrackingService().confirm_print(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_operations",
                note=request.POST.get("print_note", ""),
                request_token=request.POST.get("request_token", ""),
            )
        except ValidationError as exc:
            print_error = "; ".join(exc.messages)
            job = production_workflow_service.get_or_create_for_order(
                order=self._staff_order(order_public_id)
            )
        if job is None:
            raise Http404
        if print_error:
            response = self._render_workspace(request, print_error=print_error)
            return with_toast(response, print_error, "error")
        message = "Impression confirmée et historisée." if created else "Impression déjà confirmée."
        response = self._render_workspace(request, feedback=message)
        return with_toast(response, message, "success" if created else "info")


class StaffAtelierOperationMeterageView(StaffAtelierOperationsContextMixin, View):
    required_permissions = (
        *StaffAtelierOperationsPermissionMixin.required_permissions,
        "orders.change_order",
    )

    def post(self, request, order_public_id):
        order = self._staff_order(order_public_id)
        raw = request.POST.get("order_meterage_override_linear_m", "")
        try:
            upload_service.set_staff_order_meterage_linear_override(
                order=order,
                actor=request.user,
                raw_value=raw,
            )
        except ValidationError as exc:
            message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            response = self._render_workspace(request, meterage_error=message)
            return with_toast(response, message, "error")
        message = "Métrage enregistré."
        order.refresh_from_db()
        if order.pricing_status == "priced":
            message = "Métrage enregistré — tarif recalculé et visible côté client."
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
