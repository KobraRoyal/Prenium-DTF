from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.portal.htmx import with_toast
from apps.portal.services.production_panel_context import build_production_panel_context
from apps.portal.views_common import (
    access_scope_service,
    order_service,
    production_workflow_service,
)
from apps.portal.views_staff import StaffOrderContextMixin


class StaffOrderPanelProductionView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/production.html"

    def dispatch(self, request, *args, **kwargs):
        if not access_scope_service.can_access_staff_portal(request.user) or any(
            not request.user.has_perm(permission)
            for permission in ("orders.view_order", "production.view_productionjob")
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _production_panel_context(
        self,
        request,
        job,
        transition_error: str = "",
        handover_date_error: str = "",
    ):
        return build_production_panel_context(
            request=request,
            order=self.order,
            job=job,
            transition_error=transition_error,
            handover_date_error=handover_date_error,
        )

    def get(self, request, order_public_id):
        _, job = production_workflow_service.get_staff_job(
            order_public_id=self.order.public_id,
            actor=request.user,
            source="staff_portal",
        )
        if job is None:
            raise Http404
        self.order.refresh_from_db()
        return render(
            request,
            self.template_name,
            self._production_panel_context(request, job, ""),
        )

    def post(self, request, order_public_id):
        if request.POST.get("action") == "update_handover_date":
            if not request.user.has_perm("orders.change_order"):
                raise PermissionDenied
            handover_date_error = ""
            try:
                updated_order = order_service.update_estimated_handover_date(
                    order_public_id=self.order.public_id,
                    value=request.POST.get("estimated_handover_date", ""),
                    actor=request.user,
                    source="staff_portal",
                )
                if updated_order is None:
                    raise Http404
            except ValidationError as exc:
                handover_date_error = "; ".join(exc.messages)
            self.order = order_service.get_staff_order(self.order.public_id) or self.order
            _, job = production_workflow_service.get_staff_job(
                order_public_id=self.order.public_id,
                actor=request.user,
                source="staff_portal",
            )
            if job is None:
                raise Http404
            response = render(
                request,
                self.template_name,
                self._production_panel_context(
                    request,
                    job,
                    handover_date_error=handover_date_error,
                ),
            )
            if handover_date_error:
                return with_toast(response, handover_date_error, "error")
            return with_toast(response, "Date prévisionnelle enregistrée.", "success")
        if not request.user.has_perm("production.transition_productionjob"):
            raise PermissionDenied
        transition_error = ""
        try:
            _, job, _transition = production_workflow_service.transition_job(
                order_public_id=self.order.public_id,
                to_status=request.POST.get("to_status", ""),
                actor=request.user,
                reason=request.POST.get("reason", ""),
                source="staff_portal",
            )
        except ValidationError as exc:
            job = production_workflow_service.get_or_create_for_order(order=self.order)
            transition_error = "; ".join(exc.messages)
        self.order.refresh_from_db()
        response = render(
            request,
            self.template_name,
            self._production_panel_context(request, job, transition_error),
        )
        if transition_error:
            return with_toast(response, transition_error, "error")
        return with_toast(response, "Transition enregistree.", "success")
