from __future__ import annotations

from django.conf import settings
from django.shortcuts import render
from django.views import View

from apps.portal.views_common import (
    StaffDomainPermissionMixin,
    badge_tone_for_status,
    order_service,
    status_label,
)
from apps.production.services.staff_order_list_filters import StaffOrderListFilterService

staff_order_list_filter_service = StaffOrderListFilterService()


class StaffOrderListView(StaffDomainPermissionMixin, View):
    template_name = "portal/staff/orders_list.html"
    results_partial = "portal/staff/partials/orders_list_results.html"
    required_permission = "orders.view_order"

    def get(self, request):
        active_queue = staff_order_list_filter_service.normalize_queue(request.GET.get("queue"))
        active_period = staff_order_list_filter_service.normalize_period(request.GET.get("period"))
        search_query = request.GET.get("q", "").strip()[:120]
        base_queryset = order_service.list_staff_orders()
        queue_counts = staff_order_list_filter_service.count_by_queue(base_queryset)
        filtered_queryset = staff_order_list_filter_service.apply_filter(
            base_queryset,
            queue=active_queue,
        )
        filtered_queryset = staff_order_list_filter_service.apply_period_filter(
            filtered_queryset,
            period=active_period,
        )
        filtered_queryset = staff_order_list_filter_service.apply_search(
            filtered_queryset,
            query=search_query,
        )
        filtered_queryset = staff_order_list_filter_service.apply_operational_order(
            filtered_queryset
        )
        page_obj = order_service.paginate_orders(
            filtered_queryset,
            page_number=request.GET.get("page"),
            page_size=settings.STAFF_ORDER_LIST_PAGE_SIZE,
        )
        context = {
            "orders": page_obj.object_list,
            "page_obj": page_obj,
            "active_queue": active_queue,
            "active_period": active_period,
            "active_queue_label": staff_order_list_filter_service.label_for(active_queue),
            "active_period_label": staff_order_list_filter_service.label_for_period(active_period),
            "search_query": search_query,
            "queue_tabs": staff_order_list_filter_service.build_tabs(
                active_queue=active_queue,
                counts=queue_counts,
            ),
            "period_tabs": staff_order_list_filter_service.build_period_tabs(
                active_period=active_period,
            ),
            "nav_mode": "staff",
            "nav_key": "staff-orders",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }
        if request.headers.get("HX-Request"):
            return render(request, self.results_partial, context)
        return render(request, self.template_name, context)
