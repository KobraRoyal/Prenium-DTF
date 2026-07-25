from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.portal.views_common import (
    StaffDomainPermissionMixin,
    StaffPortalMixin,
    badge_tone_for_status,
    order_pricing_service,
    order_service,
    status_label,
)
from apps.production.models import ProductionJob
from apps.production.services.dashboard import AtelierDashboardService
from apps.uploads.models import OrderDriveFolder

atelier_dashboard_service = AtelierDashboardService()


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
        can_price_order = can_price and self.order.uses_atelier_pricing()
        can_delete_perm = request.user.has_perm("orders.delete_atelier_order")
        delete_block_reason = (
            order_service.staff_delete_block_reason(self.order) if can_delete_perm else None
        )
        can_delete_order = can_delete_perm and delete_block_reason is None
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
        staff_order_focus = atelier_dashboard_service.build_order_focus(order=self.order)
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "production_job": production_job,
                "order_drive_url": order_drive_url,
                "staff_order_focus": staff_order_focus,
                "can_price_order": can_price_order,
                "can_delete_order": can_delete_order,
                "can_delete_perm": can_delete_perm,
                "delete_block_reason": delete_block_reason,
                "price_error": request.GET.get("price_error", ""),
                "delete_error": request.GET.get("delete_error", ""),
                "priced_ok": request.GET.get("priced") == "1",
                "nav_mode": "staff",
                "nav_key": "staff-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class StaffOrderDeleteView(StaffPortalMixin, View):
    """Soft-cancel Atelier : retire la commande de la file sans hard-delete."""

    def post(self, request, order_public_id):
        if not request.user.has_perm("orders.delete_atelier_order"):
            raise PermissionDenied
        order = order_service.get_staff_order(order_public_id)
        if order is None:
            raise Http404
        detail_url = reverse(
            "portal:staff-order-detail",
            kwargs={"order_public_id": order_public_id},
        )
        try:
            order_service.delete_staff_order(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_portal",
                reason=request.POST.get("reason", ""),
            )
        except ValidationError as exc:
            messages_list = getattr(exc, "messages", None) or [str(exc)]
            return HttpResponseRedirect(
                f"{detail_url}?delete_error={' '.join(messages_list)[:200]}"
            )
        return HttpResponseRedirect(reverse("portal:staff-order-list") + "?deleted=1")
