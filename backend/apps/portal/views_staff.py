from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.orders.models import Order
from apps.portal.views_common import (
    StaffDomainPermissionMixin,
    StaffPortalMixin,
    badge_tone_for_status,
    order_pricing_service,
    order_service,
    status_label,
)
from apps.production.models import ProductionJob
from apps.uploads.models import OrderDriveFolder


class StaffOrderPriceView(StaffPortalMixin, View):
    def post(self, request, order_public_id):
        if not request.user.has_perm("orders.change_order"):
            raise PermissionDenied
        order = order_service.get_staff_order(order_public_id)
        if order is None:
            raise Http404
        try:
            order_pricing_service.compute_and_persist_order_pricing(
                order=order,
                actor=request.user,
                source="staff_portal",
            )
        except ValidationError as exc:
            messages = getattr(exc, "messages", None) or [str(exc)]
            detail_url = reverse(
                "portal:staff-order-detail",
                kwargs={"order_public_id": order_public_id},
            )
            return HttpResponseRedirect(f"{detail_url}?price_error={' '.join(messages)[:200]}")
        detail_url = reverse(
            "portal:staff-order-detail",
            kwargs={"order_public_id": order_public_id},
        )
        return HttpResponseRedirect(f"{detail_url}?priced=1")


class StaffDashboardView(StaffPortalMixin, View):
    template_name = "portal/staff/dashboard.html"

    def get(self, request):
        can_read_orders = request.user.has_perm("orders.view_order")
        recent_orders = order_service.list_staff_orders()[:8] if can_read_orders else []
        access_label = "Autorise" if can_read_orders else "Refuse"
        kpi_rows = [
            {"label": "Acces commandes", "value": access_label, "hint": None},
            {
                "label": "Commandes affichees",
                "value": str(len(recent_orders)),
                "hint": None,
            },
        ]
        return render(
            request,
            self.template_name,
            {
                "recent_orders": recent_orders,
                "can_read_orders": can_read_orders,
                "kpi_rows": kpi_rows,
                "nav_mode": "staff",
                "nav_key": "staff-dashboard",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderListView(StaffDomainPermissionMixin, View):
    template_name = "portal/staff/orders_list.html"
    required_permission = "orders.view_order"

    def get(self, request):
        page_obj = order_service.paginate_orders(
            order_service.list_staff_orders(),
            page_number=request.GET.get("page"),
            page_size=settings.STAFF_ORDER_LIST_PAGE_SIZE,
        )
        return render(
            request,
            self.template_name,
            {
                "orders": page_obj.object_list,
                "page_obj": page_obj,
                "nav_mode": "staff",
                "nav_key": "staff-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderContextMixin(StaffDomainPermissionMixin):
    required_permission = "orders.view_order"
    order = None

    def dispatch(self, request, *args, **kwargs):
        order = order_service.get_staff_order(kwargs.get("order_public_id"))
        if order is None:
            raise Http404
        self.order = order
        return super().dispatch(request, *args, **kwargs)


class StaffOrderDetailView(StaffOrderContextMixin, View):
    template_name = "portal/staff/order_detail.html"

    def get(self, request, order_public_id):
        can_price = request.user.has_perm("orders.change_order")
        deferred = self.order.billing_mode == Order.BillingMode.DEFERRED
        try:
            production_job = self.order.production_job
        except ProductionJob.DoesNotExist:
            production_job = None
        drive_folder = (
            OrderDriveFolder.objects.filter(order_id=self.order.pk).only("order_folder_id").first()
        )
        order_drive_url = (
            drive_folder.google_drive_folder_url() if drive_folder is not None else None
        )
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "production_job": production_job,
                "order_drive_url": order_drive_url,
                "can_price_order": can_price and deferred,
                "price_error": request.GET.get("price_error", ""),
                "priced_ok": request.GET.get("priced") == "1",
                "nav_mode": "staff",
                "nav_key": "staff-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
