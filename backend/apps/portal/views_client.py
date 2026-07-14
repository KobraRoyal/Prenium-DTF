from __future__ import annotations

from collections import Counter

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.b2b_order_projects.permissions import b2b_order_projects_enabled_for_customer
from apps.b2b_order_projects.services import (
    B2BOrderProjectService,
    B2BOrderReorderService,
    ProjectDomainError,
)
from apps.core.public_refs import short_public_ref
from apps.orders.references import order_client_reference
from apps.orders.services.client_timeline import build_client_order_status_history
from apps.portal.views_common import (
    ClientOwnerRequiredMixin,
    ScopedCustomerMixin,
    access_scope_service,
    badge_tone_for_status,
    billing_service,
    order_service,
    status_label,
    upload_service,
)
from apps.uploads.services.assets import AssetService

project_service = B2BOrderProjectService()
reorder_service = B2BOrderReorderService()
asset_service = AssetService()


class ClientDashboardView(LoginRequiredMixin, View):
    template_name = "portal/client/dashboard.html"

    def get(self, request):
        scope = access_scope_service.get_user_scope(request.user)
        memberships = list(scope.memberships)
        selected_membership = memberships[0] if memberships else None
        customer = None
        recent_orders = []
        recent_projects = []
        project_feature_enabled = False
        if selected_membership is not None:
            customer = (
                access_scope_service.get_customer_queryset(request.user)
                .filter(public_id=selected_membership.customer_public_id)
                .first()
            )
            if customer is not None:
                orders_qs = order_service.list_customer_orders(customer)
                recent_orders = list(orders_qs[:5])
                orders_count = orders_qs.count()
                project_feature_enabled = b2b_order_projects_enabled_for_customer(customer)
                projects_in_progress_count = 0
                recent_projects = []
                if project_feature_enabled:
                    projects_qs = project_service.list_customer_projects_in_progress(customer)
                    recent_projects = project_service.attach_can_delete(list(projects_qs[:5]))
                    projects_in_progress_count = projects_qs.count()
                if project_feature_enabled:
                    new_order_url = reverse(
                        "portal:client-order-project-create",
                        kwargs={"customer_public_id": customer.public_id},
                    )
                else:
                    new_order_url = reverse(
                        "portal:client-checkout",
                        kwargs={"customer_public_id": customer.public_id},
                    )
            else:
                orders_count = 0
                projects_in_progress_count = 0
                new_order_url = ""
        else:
            orders_count = 0
            projects_in_progress_count = 0
            new_order_url = ""
        kpi_rows = []
        if selected_membership is not None:
            kpi_rows = [
                {
                    "label": "Compte client",
                    "value": selected_membership.customer_name,
                    "hint": f"Role : {status_label(str(selected_membership.role))}",
                },
                {
                    "label": "Commandes",
                    "value": str(orders_count if customer is not None else 0),
                    "hint": None,
                },
            ]
            if project_feature_enabled:
                kpi_rows.append(
                    {
                        "label": "Commandes à finaliser",
                        "value": str(
                            projects_in_progress_count if customer is not None else 0
                        ),
                        "hint": None,
                    }
                )
        context = {
            "scope": scope,
            "memberships": memberships,
            "selected_membership": selected_membership,
            "customer": customer,
            "recent_orders": recent_orders,
            "recent_projects": recent_projects,
            "orders_count": orders_count if selected_membership is not None else 0,
            "projects_in_progress_count": (
                projects_in_progress_count if selected_membership is not None else 0
            ),
            "new_order_url": new_order_url if selected_membership is not None else "",
            "project_feature_enabled": project_feature_enabled,
            "kpi_rows": kpi_rows,
            "nav_mode": "client",
            "nav_key": "client-dashboard",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }
        return render(request, self.template_name, context)


class ClientOrderListView(ScopedCustomerMixin, View):
    template_name = "portal/client/orders_list.html"
    results_partial = "portal/client/partials/client_orders_list_results.html"

    def get(self, request, customer_public_id):
        context = self._build_context(request)
        if request.headers.get("HX-Request"):
            return render(request, self.results_partial, context)
        return render(request, self.template_name, context)

    def _build_context(self, request):
        search_query = request.GET.get("q", "").strip()
        orders_qs = order_service.list_customer_orders(self.customer)
        if search_query:
            orders_qs = order_service.filter_customer_orders(orders_qs, query=search_query)
        page_obj = order_service.paginate_orders(
            orders_qs,
            page_number=request.GET.get("page"),
            page_size=settings.ORDER_LIST_PAGE_SIZE,
        )
        return {
            "customer": self.customer,
            "orders": page_obj.object_list,
            "page_obj": page_obj,
            "search_query": search_query,
            "nav_mode": "client",
            "nav_key": "client-orders",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }


class ClientOrderContextMixin(ScopedCustomerMixin):
    def get_order_or_404(self, order_public_id):
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return order

    def client_order_context(self, *, order, **extra):
        context = {
            "customer": self.customer,
            "customer_membership": self.customer_membership,
            "order": order,
            "order_short_ref": short_public_ref(order.public_id),
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }
        context.update(extra)
        return context


class ClientOrderDetailView(ClientOrderContextMixin, View):
    template_name = "portal/client/order_detail.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        return render(
            request,
            self.template_name,
            self.client_order_context(
                order=order,
                active_panel=request.GET.get("panel", ""),
            )
            | {
                "order_client_label": order_client_reference(order),
                "nav_mode": "client",
                "nav_key": "client-orders",
            },
        )


class ClientOrderPanelUploadsView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/uploads.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        _order, uploads = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        return render(
            request,
            self.template_name,
            self.client_order_context(
                order=order,
                uploads=uploads,
                reorder_enabled=b2b_order_projects_enabled_for_customer(self.customer),
                active_panel="uploads",
            ),
        )


class ClientOrderPanelInspectionView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/inspection.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        _order, uploads = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order.public_id,
        )
        inspections = [upload.inspection for upload in uploads if hasattr(upload, "inspection")]
        inspection_counter = Counter(inspection.status for inspection in inspections)
        return render(
            request,
            self.template_name,
            {
                "order": order,
                "uploads": uploads,
                "inspections": inspections,
                "inspection_counter": inspection_counter,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelProductionView(ClientOrderContextMixin, View):
    template_name = "portal/client/panels/production.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        return render(
            request,
            self.template_name,
            self.client_order_context(
                order=order,
                status_history=build_client_order_status_history(order),
                active_panel="production",
            ),
        )


class ClientOrderPanelShippingView(ClientOwnerRequiredMixin, ClientOrderContextMixin, View):
    template_name = "portal/client/panels/shipping.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        shipment = None
        try:
            shipment = order.shipment
        except ObjectDoesNotExist:
            shipment = None
        return render(
            request,
            self.template_name,
            self.client_order_context(order=order, shipment=shipment, active_panel="shipping"),
        )


class ClientOrderPanelBillingView(ClientOwnerRequiredMixin, ClientOrderContextMixin, View):
    template_name = "portal/client/panels/billing.html"

    def get(self, request, customer_public_id, order_public_id):
        order, payment, invoice = billing_service.get_customer_billing(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return render(
            request,
            self.template_name,
            self.client_order_context(
                order=order,
                payment=payment,
                invoice=invoice,
                active_panel="billing",
            ),
        )


class ClientOrderUploadPreviewView(ClientOrderContextMixin, View):
    def get(self, request, customer_public_id, order_public_id, upload_public_id):
        order = self.get_order_or_404(order_public_id)
        _order, order_upload = upload_service.get_customer_order_upload(
            customer=self.customer,
            order_public_id=order.public_id,
            upload_public_id=upload_public_id,
        )
        if order_upload is None:
            raise Http404
        preview = asset_service.prepare_order_upload_preview(order_upload=order_upload)
        if preview is None:
            raise Http404
        preview_file, content_type = preview
        preview_file.open("rb")
        response = FileResponse(preview_file, content_type=content_type)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response


class ClientOrderUploadDownloadView(ClientOrderContextMixin, View):
    def get(self, request, customer_public_id, order_public_id, upload_public_id):
        order_upload = upload_service.download_customer_order_upload(
            customer=self.customer,
            actor=request.user,
            customer_membership=self.customer_membership,
            order_public_id=order_public_id,
            upload_public_id=upload_public_id,
            source="client_portal.order_upload_download",
        )
        if order_upload is None:
            raise Http404
        order_upload.file.open("rb")
        return FileResponse(
            order_upload.file,
            as_attachment=True,
            filename=order_upload.original_filename,
            content_type=order_upload.mime_type,
        )


class ClientOrderReorderView(ClientOrderContextMixin, View):
    def post(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        try:
            project = reorder_service.create_reorder_from_order(
                customer=self.customer,
                order=order,
                actor=request.user,
                source="client_portal.order_reorder",
            )
        except ProjectDomainError as error:
            detail_url = reverse(
                "portal:client-order-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "order_public_id": order.public_id,
                },
            )
            return HttpResponseRedirect(
                f"{detail_url}?panel=uploads&reorder_error={error.code.lower()}"
            )
        return HttpResponseRedirect(
            reverse(
                "portal:client-order-project-detail",
                kwargs={
                    "customer_public_id": self.customer.public_id,
                    "project_public_id": project.public_id,
                },
            )
        )
