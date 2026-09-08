from __future__ import annotations

from datetime import datetime, timedelta

from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.b2b_order_projects.services import B2BOrderProjectService
from apps.billing.models import Payment
from apps.billing.services.production_payment_gate import attach_awaits_client_payment
from apps.orders.models import Order
from apps.portal import dashboard_focus
from apps.portal.views_common import ScopedCustomerMixin, order_service
from apps.production.models import ProductionJob

project_service = B2BOrderProjectService()


class ClientDashboardResultsView(ScopedCustomerMixin, View):
    """Retourne la section Commandes, filtrée depuis un graphique du tableau de bord."""

    template_name = "portal/client/partials/dashboard_orders.html"

    def get(self, request, customer_public_id):
        kind = (request.GET.get("kind") or "").strip()
        month_value = (request.GET.get("month") or "").strip()
        month_start = None
        if month_value:
            try:
                month_start = datetime.strptime(month_value, "%Y-%m").date().replace(day=1)
            except ValueError:
                month_start = None

        orders = order_service.list_customer_orders(self.customer)
        context = {
            "customer": self.customer,
            "orders": [],
            "orders_count": 0,
            "dashboard_results_all_url": reverse(
                "portal:client-order-list",
                kwargs={"customer_public_id": self.customer.public_id},
            ),
            "dashboard_results_all_label": "Toutes les commandes",
        }
        if kind == "projects":
            projects = project_service.attach_can_delete(
                list(
                    project_service.list_customer_projects_in_progress(self.customer).filter(
                        status__in=dashboard_focus.ACTIONABLE_PROJECT_STATUSES
                    )[:5]
                )
            )
            return render(
                request,
                self.template_name,
                context
                | {
                    "dashboard_results_title": "Dossiers à reprendre",
                    "dashboard_results_description": (
                        "Complétez ou confirmez les visuels pour poursuivre."
                    ),
                    "dashboard_results_projects": projects,
                    "dashboard_results_all_url": reverse(
                        "portal:client-order-project-list",
                        kwargs={"customer_public_id": self.customer.public_id},
                    ),
                    "dashboard_results_all_label": "Tous les dossiers",
                    "dashboard_results_empty": "Aucun dossier à reprendre.",
                },
            )

        financial_kind = kind in {"ordered", "paid", "awaiting"}
        if financial_kind and not dashboard_focus.can_view_client_financial_dashboard(
            self.customer_membership
        ):
            raise Http404
        if kind == "atelier":
            orders = orders.filter(
                production_job__status__in={
                    ProductionJob.Status.QUEUED,
                    ProductionJob.Status.IN_PROGRESS,
                    ProductionJob.Status.READY_TO_SHIP,
                }
            )
            title = "Commandes en atelier"
            description = "Vos commandes sont en préparation ou prêtes à expédier."
        elif kind == "tracking":
            orders = orders.filter(shipment__tracking_number__gt="")
            title = "Livraisons à suivre"
            description = "Suivez les commandes dont le transport est disponible."
        elif kind in {"ordered", "paid", "awaiting"} and month_start is not None:
            next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
            if kind == "paid":
                paid_order_ids = (
                    Payment.objects.for_customer(self.customer)
                    .filter(
                        status=Payment.Status.CAPTURED,
                        captured_at__date__gte=month_start,
                        captured_at__date__lt=next_month,
                    )
                    .values_list("order_id", flat=True)
                )
                orders = orders.filter(pk__in=paid_order_ids)
                title = f"Paiements de {month_start.strftime('%m/%Y')}"
                description = "Paiements confirmés sur la période sélectionnée."
            else:
                orders = orders.filter(
                    created_at__date__gte=month_start,
                    created_at__date__lt=next_month,
                    status=Order.Status.SUBMITTED,
                    pricing_status=Order.PricingStatus.PRICED,
                ).exclude(status=Order.Status.CANCELLED)
                if kind == "awaiting":
                    orders = [
                        order
                        for order in attach_awaits_client_payment(list(orders))
                        if order.awaits_client_payment
                    ]
                    title = f"Règlements à finaliser de {month_start.strftime('%m/%Y')}"
                    description = "Commandes qui attendent votre règlement."
                else:
                    title = f"Commandes de {month_start.strftime('%m/%Y')}"
                    description = "Commandes tarifées sur la période sélectionnée."
        else:
            raise Http404

        orders = attach_awaits_client_payment(list(orders))
        return render(
            request,
            self.template_name,
            context
            | {
                "orders": orders[:5],
                "orders_count": len(orders),
                "dashboard_results_title": title,
                "dashboard_results_description": description,
                "dashboard_results_empty": "Aucune commande à afficher pour cette sélection.",
            },
        )
