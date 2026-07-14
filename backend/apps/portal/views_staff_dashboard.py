from __future__ import annotations

from django.conf import settings
from django.shortcuts import render
from django.views import View

from apps.portal.views_common import StaffPortalMixin
from apps.production.services.dashboard import AtelierDashboardService

atelier_dashboard_service = AtelierDashboardService()


class StaffDashboardView(StaffPortalMixin, View):
    template_name = "portal/staff/dashboard.html"

    def get(self, request):
        can_read_orders = request.user.has_perm("orders.view_order")
        can_read_production = request.user.has_perm("production.view_productionjob")
        can_read_worklist = can_read_orders and can_read_production
        can_read_projects = bool(
            getattr(settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False)
            and request.user.has_perm("b2b_order_projects.view_b2borderproject")
        )
        dashboard = (
            atelier_dashboard_service.build_dashboard(active_tab=request.GET.get("queue"))
            if can_read_worklist
            else {
                "rows": [],
                "metrics": {},
                "printable_count": 0,
                "tabs": [],
                "active_tab": "to_review",
            }
        )
        metrics = dashboard["metrics"]
        kpi_rows = [
            {
                "label": "À contrôler",
                "value": str(metrics.get("pending_review", 0)),
                "hint": "Validation Atelier requise",
            },
            {
                "label": "Corrections client",
                "value": str(metrics.get("changes_requested", 0)),
                "hint": "Fichiers à remplacer",
            },
            {
                "label": "OF prêts",
                "value": str(metrics.get("ready_to_print", 0)),
                "hint": "Validés et en attente",
            },
            {
                "label": "En production",
                "value": str(metrics.get("in_production", 0)),
                "hint": "Travaux lancés ou bloqués",
            },
        ]
        return render(
            request,
            self.template_name,
            {
                "worklist_rows": dashboard["rows"],
                "printable_count": dashboard["printable_count"],
                "worklist_tabs": dashboard["tabs"],
                "active_worklist_tab": dashboard["active_tab"],
                "ready_to_print_count": metrics.get("ready_to_print", 0),
                "can_read_orders": can_read_orders,
                "can_read_worklist": can_read_worklist,
                "can_batch_print": can_read_worklist,
                "can_read_projects": can_read_projects,
                "kpi_rows": kpi_rows,
                "batch_error": request.GET.get("batch_error", ""),
                "nav_mode": "staff",
                "nav_key": "staff-dashboard",
            },
        )
