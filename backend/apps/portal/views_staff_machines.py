from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.portal.htmx import with_toast
from apps.portal.views_common import StaffDomainPermissionMixin, access_scope_service
from apps.production.models import ProductionMachine, ProductionPrintRecord
from apps.production.services.machine_fleet import MachineFleetService

machine_fleet_service = MachineFleetService()


def machine_fleet_context(
    *,
    request,
    form_error: str = "",
    form_values: dict | None = None,
    edit_machine_public_id: str = "",
):
    can_read_print_ledger = all(
        request.user.has_perm(permission)
        for permission in ("orders.view_order", "production.view_productionjob")
    )
    return {
        "machines": machine_fleet_service.list_machines(actor=request.user),
        "fleet_summary": machine_fleet_service.fleet_summary(actor=request.user),
        "recent_prints": (
            ProductionPrintRecord.objects.select_related(
                "production_job",
                "production_job__order",
                "production_job__order__customer",
                "machine",
                "recorded_by",
            )[:12]
            if can_read_print_ledger
            else []
        ),
        "can_read_print_ledger": can_read_print_ledger,
        "machine_statuses": ProductionMachine.Status.choices,
        "can_manage_machines": request.user.has_perm("production.manage_productionmachine"),
        "form_error": form_error,
        "form_values": form_values or {},
        "edit_machine_public_id": str(edit_machine_public_id or ""),
    }


class StaffMachineFleetView(StaffDomainPermissionMixin, View):
    template_name = "portal/staff/machines/index.html"
    required_permission = "production.view_productionmachine"

    def get(self, request):
        return render(
            request,
            self.template_name,
            {
                **machine_fleet_context(request=request),
                "nav_mode": "staff",
                "nav_key": "staff-machines",
            },
        )


class MachineMutationMixin(StaffDomainPermissionMixin):
    required_permission = "production.manage_productionmachine"
    partial_template_name = "portal/staff/machines/_fleet_content.html"
    page_template_name = "portal/staff/machines/index.html"

    def dispatch(self, request, *args, **kwargs):
        if not access_scope_service.can_access_staff_portal(
            request.user
        ) or not request.user.has_perm(self.required_permission):
            record_event(
                action="production.machine.permission_rejected",
                actor=(request.user if request.user.is_authenticated else None),
                status=AuditLogEntry.Status.FAILURE,
                message="Requête Atelier refusée.",
                metadata={"source": "staff_portal", "reason": "permission_denied"},
            )
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _render_result(
        self,
        *,
        request,
        message: str,
        variant: str,
        form_error: str = "",
        form_values: dict | None = None,
        edit_machine_public_id: str = "",
    ):
        context = machine_fleet_context(
            request=request,
            form_error=form_error,
            form_values=form_values,
            edit_machine_public_id=edit_machine_public_id,
        )
        if request.headers.get("HX-Request") == "true":
            response = render(request, self.partial_template_name, context)
            return with_toast(response, message, variant)
        if form_error:
            return render(
                request,
                self.page_template_name,
                {
                    **context,
                    "nav_mode": "staff",
                    "nav_key": "staff-machines",
                },
                status=400,
            )
        return HttpResponseRedirect(reverse("portal:staff-machine-fleet"))


class StaffMachineCreateView(MachineMutationMixin, View):
    def post(self, request):
        try:
            machine_fleet_service.create_machine(
                actor=request.user,
                source="staff_portal",
                data=request.POST,
            )
        except ValidationError as exc:
            error = "; ".join(exc.messages)
            return self._render_result(
                request=request,
                message=error,
                variant="error",
                form_error=error,
                form_values=request.POST,
            )
        return self._render_result(
            request=request,
            message="Imprimante ajoutée au parc.",
            variant="success",
        )


class StaffMachineUpdateView(MachineMutationMixin, View):
    def post(self, request, machine_public_id):
        try:
            machine_fleet_service.update_machine(
                machine_public_id=machine_public_id,
                actor=request.user,
                source="staff_portal",
                data=request.POST,
            )
        except ValidationError as exc:
            error = "; ".join(exc.messages)
            return self._render_result(
                request=request,
                message=error,
                variant="error",
                form_error=error,
                form_values=request.POST,
                edit_machine_public_id=machine_public_id,
            )
        return self._render_result(
            request=request,
            message="Imprimante mise à jour.",
            variant="success",
        )
