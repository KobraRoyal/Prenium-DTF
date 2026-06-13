from __future__ import annotations

from collections import Counter

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import render
from django.views import View

from apps.portal.views_common import (
    ScopedCustomerMixin,
    access_scope_service,
    badge_tone_for_status,
    billing_service,
    order_service,
    status_label,
    upload_service,
)


class ClientDashboardView(LoginRequiredMixin, View):
    template_name = "portal/client/dashboard.html"

    def get(self, request):
        scope = access_scope_service.get_user_scope(request.user)
        memberships = list(scope.memberships)
        selected_membership = memberships[0] if memberships else None
        customer = None
        recent_orders = []
        if selected_membership is not None:
            customer = (
                access_scope_service.get_customer_queryset(request.user)
                .filter(public_id=selected_membership.customer_public_id)
                .first()
            )
            if customer is not None:
                recent_orders = list(order_service.list_customer_orders(customer)[:5])
        kpi_rows = []
        if selected_membership is not None:
            kpi_rows = [
                {
                    "label": "Compte client",
                    "value": selected_membership.customer_name,
                    "hint": f"Role : {status_label(str(selected_membership.role))}",
                },
                {
                    "label": "Commandes recentes",
                    "value": str(len(recent_orders)),
                    "hint": None,
                },
            ]
        context = {
            "scope": scope,
            "memberships": memberships,
            "selected_membership": selected_membership,
            "customer": customer,
            "recent_orders": recent_orders,
            "kpi_rows": kpi_rows,
            "nav_mode": "client",
            "nav_key": "client-dashboard",
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }
        return render(request, self.template_name, context)


class ClientOrderListView(ScopedCustomerMixin, View):
    template_name = "portal/client/orders_list.html"

    def get(self, request, customer_public_id):
        page_obj = order_service.paginate_orders(
            order_service.list_customer_orders(self.customer),
            page_number=request.GET.get("page"),
            page_size=settings.ORDER_LIST_PAGE_SIZE,
        )
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "orders": page_obj.object_list,
                "page_obj": page_obj,
                "nav_mode": "client",
                "nav_key": "client-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderContextMixin(ScopedCustomerMixin):
    def get_order_or_404(self, order_public_id):
        order = order_service.get_customer_order(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return order


class ClientOrderDetailView(ClientOrderContextMixin, View):
    template_name = "portal/client/order_detail.html"

    def get(self, request, customer_public_id, order_public_id):
        order = self.get_order_or_404(order_public_id)
        return render(
            request,
            self.template_name,
            {
                "customer": self.customer,
                "order": order,
                "nav_mode": "client",
                "nav_key": "client-orders",
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
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
            {
                "customer": self.customer,
                "order": order,
                "uploads": uploads,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
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
        stage = "Traitement en cours"
        detail = "Votre commande est en cours de suivi par notre equipe."
        production_job = None
        try:
            production_job = order.production_job
        except ObjectDoesNotExist:
            production_job = None

        if production_job is not None:
            map_stage = {
                "queued": (
                    "Commande planifiee",
                    "Vos fichiers sont valides et la production est en file atelier.",
                ),
                "in_progress": (
                    "Commande en production",
                    "La production est en cours. Prochaine etape: preparation expedition.",
                ),
                "ready_to_ship": (
                    "Commande prete a expedier",
                    "La production est terminee. Expedition imminente.",
                ),
                "blocked": (
                    "Commande en attente d'action",
                    "Un point est en attente de resolution avant reprise.",
                ),
                "completed": (
                    "Production terminee",
                    "La commande est finalisee cote atelier.",
                ),
            }
            stage, detail = map_stage.get(
                production_job.status,
                ("Traitement en cours", "La commande progresse dans notre workflow."),
            )
        elif order.status == "draft":
            stage = "En attente de validation"
            detail = "Finalisez la commande pour lancer la production."
        elif order.status == "submitted":
            stage = "Commande en file de traitement"
            detail = "Votre commande est bien recue et sera traitee rapidement."

        return render(
            request,
            self.template_name,
            {
                "order": order,
                "stage": stage,
                "detail": detail,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelShippingView(ClientOrderContextMixin, View):
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
            {
                "order": order,
                "shipment": shipment,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )


class ClientOrderPanelBillingView(ClientOrderContextMixin, View):
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
            {
                "order": order,
                "payment": payment,
                "invoice": invoice,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
