from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.portal.htmx import with_toast
from apps.portal.views_common import access_scope_service, production_workflow_service
from apps.portal.views_staff import StaffOrderContextMixin
from apps.portal.views_staff_production import production_panel_context
from apps.production.services.machine_assignments import (
    ProductionMachineAssignmentService,
)
from apps.production.services.print_tracking import ProductionPrintTrackingService


class StaffOrderMachinePermissionMixin:
    required_permissions: tuple[str, ...] = ()
    rejection_action = ""

    def dispatch(self, request, *args, **kwargs):
        if not access_scope_service.can_access_staff_portal(request.user) or any(
            not request.user.has_perm(permission) for permission in self.required_permissions
        ):
            self._record_http_rejection(request=request, reason="permission_denied")
            raise PermissionDenied
        try:
            return super().dispatch(request, *args, **kwargs)
        except Http404:
            self._record_http_rejection(request=request, reason="object_not_found")
            raise

    def _record_http_rejection(self, *, request, reason: str) -> None:
        record_event(
            action=self.rejection_action,
            actor=(request.user if request.user.is_authenticated else None),
            status=AuditLogEntry.Status.FAILURE,
            message="Requête Atelier refusée.",
            metadata={"source": "staff_portal", "reason": reason},
        )


class StaffOrderMachineAssignmentView(
    StaffOrderMachinePermissionMixin, StaffOrderContextMixin, View
):
    template_name = "portal/staff/panels/production.html"
    rejection_action = "production.machine_assignment.rejected"
    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
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
                source="staff_portal",
                reason=request.POST.get("machine_reason", ""),
            )
        except ValidationError as exc:
            job = production_workflow_service.get_or_create_for_order(order=self.order)
            machine_error = "; ".join(exc.messages)
        job = production_workflow_service._get_job_queryset().get(pk=job.pk)
        response = render(
            request,
            self.template_name,
            production_panel_context(
                request=request,
                order=self.order,
                job=job,
                machine_error=machine_error,
            ),
        )
        if machine_error:
            return with_toast(response, machine_error, "error")
        if not changed:
            return with_toast(response, "Cette imprimante est déjà attribuée.", "info")
        return with_toast(response, "Imprimante attribuée à l’OF.", "success")


class StaffOrderPrintConfirmView(
    StaffOrderMachinePermissionMixin, StaffOrderContextMixin, View
):
    template_name = "portal/staff/panels/production.html"
    rejection_action = "production.print.confirmation_rejected"
    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
        "production.confirm_productionprint",
    )

    def post(self, request, order_public_id):
        print_error = ""
        created = False
        try:
            job, _print_record, created = ProductionPrintTrackingService().confirm_print(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_portal",
                note=request.POST.get("print_note", ""),
                request_token=request.POST.get("request_token", ""),
            )
        except ValidationError as exc:
            job = production_workflow_service.get_or_create_for_order(order=self.order)
            print_error = "; ".join(exc.messages)
        job = production_workflow_service._get_job_queryset().get(pk=job.pk)
        response = render(
            request,
            self.template_name,
            production_panel_context(
                request=request,
                order=self.order,
                job=job,
                print_error=print_error,
            ),
        )
        if print_error:
            return with_toast(response, print_error, "error")
        if not created:
            return with_toast(response, "Impression déjà confirmée.", "info")
        return with_toast(response, "Impression confirmée et historisée.", "success")
