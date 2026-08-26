from django.conf import settings
from django.shortcuts import render
from django.views import View

from apps.portal.views_common import StaffPortalMixin
from apps.production.services.dashboard import AtelierDashboardService
from apps.production.services.manufacturing_order_batch import ManufacturingOrderBatchService

atelier_dashboard_service = AtelierDashboardService()


class StaffDashboardView(StaffPortalMixin, View):
    template_name = "portal/staff/dashboard.html"
    worklist_partial_template_name = "portal/staff/partials/dashboard_worklist_panel.html"

    def _build_context(self, request):
        can_read_orders = request.user.has_perm("orders.view_order")
        can_read_production = request.user.has_perm("production.view_productionjob")
        can_read_worklist = can_read_orders and can_read_production
        can_read_projects = bool(
            getattr(settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False)
            and request.user.has_perm("b2b_order_projects.view_b2borderproject")
        )
        can_read_machine_fleet = request.user.has_perm("production.view_productionmachine")
        dashboard = (
            atelier_dashboard_service.build_dashboard()
            if can_read_worklist
            else {
                "rows": [],
                "metrics": {},
                "kpi_rows": [],
                "printable_count": 0,
                "unprinted_of_total": 0,
                "unprinted_of_batch_count": 0,
                "batch_print_limit": ManufacturingOrderBatchService.max_batch_size,
            }
        )
        metrics = dashboard["metrics"]
        return {
            "worklist_rows": dashboard["rows"],
            "printable_count": dashboard["printable_count"],
            "dashboard_kpi_rows": dashboard.get("kpi_rows", []),
            "unprinted_of_total": dashboard.get("unprinted_of_total", 0),
            "unprinted_of_batch_count": dashboard.get("unprinted_of_batch_count", 0),
            "batch_print_limit": dashboard.get(
                "batch_print_limit", ManufacturingOrderBatchService.max_batch_size
            ),
            "ready_to_print_count": metrics.get("files_validated", 0),
            "can_read_orders": can_read_orders,
            "can_read_worklist": can_read_worklist,
            "can_batch_print": can_read_worklist,
            "can_read_projects": can_read_projects,
            "can_read_machine_fleet": can_read_machine_fleet,
            "batch_error": request.GET.get("batch_error", ""),
            "nav_mode": "staff",
            "nav_key": "staff-dashboard",
        }

    def get(self, request):
        context = self._build_context(request)
        if request.headers.get("HX-Request") == "true":
            return render(request, self.worklist_partial_template_name, context)
        return render(request, self.template_name, context)
