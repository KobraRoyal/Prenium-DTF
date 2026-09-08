from __future__ import annotations

from calendar import month_abbr
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import urlencode

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse
from django.utils import timezone

from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import CustomerMembership
from apps.customers.services.volume_nudge_copy import render_nudge_message
from apps.orders.models import Order
from apps.orders.references import order_business_number, order_client_reference
from apps.portal.views_common import status_label

ACTIONABLE_PROJECT_STATUSES = {
    B2BOrderProject.Status.DRAFT,
    B2BOrderProject.Status.INCOMPLETE,
    B2BOrderProject.Status.ACTION_REQUIRED,
    B2BOrderProject.Status.READY_TO_SUBMIT,
    B2BOrderProject.Status.CHANGES_REQUESTED,
    B2BOrderProject.Status.PRICE_CONFIRMATION_REQUIRED,
}


def _month_starts(*, count: int = 6) -> list[date]:
    current = timezone.localdate().replace(day=1)
    starts = []
    for offset in range(count - 1, -1, -1):
        month_index = current.year * 12 + current.month - 1 - offset
        starts.append(date(month_index // 12, month_index % 12 + 1, 1))
    return starts


def _month_label(month_start: date) -> str:
    return f"{month_abbr[month_start.month].capitalize()}."


def can_view_client_financial_dashboard(membership) -> bool:
    """Expose le pilotage financier aux rôles de gestion du compte uniquement."""
    return bool(
        membership is not None
        and membership.role in {CustomerMembership.Role.OWNER, CustomerMembership.Role.ADMIN}
    )


def _dashboard_results_url(*, customer, kind: str, month: date | None = None) -> str:
    url = reverse(
        "portal:client-dashboard-results",
        kwargs={"customer_public_id": customer.public_id},
    )
    query = {"kind": kind}
    if month is not None:
        query["month"] = month.strftime("%Y-%m")
    return f"{url}?{urlencode(query)}"


def build_client_financial_dashboard(*, customer) -> dict[str, object]:
    """Séries factuelles pour le pilotage client, limitées à un seul compte."""
    from apps.billing.models import Payment

    month_starts = _month_starts()
    start = month_starts[0]
    current_month = month_starts[-1]
    orders = list(
        Order.objects.for_customer(customer)
        .filter(
            created_at__date__gte=start,
            status=Order.Status.SUBMITTED,
            pricing_status=Order.PricingStatus.PRICED,
        )
        .exclude(status=Order.Status.CANCELLED)
        .select_related("source_b2b_order_project")
        .prefetch_related("items", "uploads")
    )
    captured_payments = list(
        Payment.objects.for_customer(customer)
        .filter(
            status=Payment.Status.CAPTURED,
            captured_at__date__gte=start,
        )
        .select_related("order", "order__source_b2b_order_project")
    )
    captured_order_ids = {payment.order_id for payment in captured_payments}
    ordered_by_month = {month: Decimal("0.00") for month in month_starts}
    paid_by_month = {month: Decimal("0.00") for month in month_starts}
    awaiting_by_month = {month: Decimal("0.00") for month in month_starts}
    awaiting_amount = Decimal("0.00")
    for order in orders:
        order_month = order.created_at.date().replace(day=1)
        if order_month in ordered_by_month:
            ordered_by_month[order_month] += order.total_amount or Decimal("0.00")
        if (
            order.billing_mode == Order.BillingMode.IMMEDIATE
            and order.pk not in captured_order_ids
            and order.total_amount > 0
            and order.uses_atelier_pricing()
        ):
            awaiting_amount += order.total_amount
            if order_month in awaiting_by_month:
                awaiting_by_month[order_month] += order.total_amount
    for payment in captured_payments:
        if payment.captured_at is None:
            continue
        payment_month = payment.captured_at.date().replace(day=1)
        if payment_month in paid_by_month:
            paid_by_month[payment_month] += payment.amount
    labels = [_month_label(month) for month in month_starts]
    return {
        "current_month_total": ordered_by_month[current_month],
        "current_month_paid": paid_by_month[current_month],
        "awaiting_payment_total": awaiting_amount,
        "trend": {
            "labels": labels,
            "ordered": [float(ordered_by_month[month]) for month in month_starts],
            "paid": [float(paid_by_month[month]) for month in month_starts],
            "awaiting": [float(awaiting_by_month[month]) for month in month_starts],
            "result_urls": {
                "ordered": [
                    _dashboard_results_url(customer=customer, kind="ordered", month=month)
                    for month in month_starts
                ],
                "paid": [
                    _dashboard_results_url(customer=customer, kind="paid", month=month)
                    for month in month_starts
                ],
                "awaiting": [
                    _dashboard_results_url(customer=customer, kind="awaiting", month=month)
                    for month in month_starts
                ],
            },
        },
    }


def build_client_operational_dashboard(
    *, customer, projects_in_progress_count: int
) -> dict[str, object]:
    """Statuts lisibles par le client : préparation, atelier, expédition."""
    from apps.production.models import ProductionJob
    from apps.shipping.models import Shipment

    in_atelier_count = ProductionJob.objects.filter(
        order__customer=customer,
        status__in={
            ProductionJob.Status.QUEUED,
            ProductionJob.Status.IN_PROGRESS,
            ProductionJob.Status.READY_TO_SHIP,
        },
    ).count()
    trackable_shipments_count = (
        Shipment.objects.for_customer(customer).filter(tracking_number__gt="").count()
    )
    return {
        "in_atelier_count": in_atelier_count,
        "trackable_shipments_count": trackable_shipments_count,
        "status_chart": {
            "labels": ["À préparer", "En atelier", "À suivre"],
            "values": [
                projects_in_progress_count,
                in_atelier_count,
                trackable_shipments_count,
            ],
            "result_urls": [
                _dashboard_results_url(customer=customer, kind="projects"),
                _dashboard_results_url(customer=customer, kind="atelier"),
                _dashboard_results_url(customer=customer, kind="tracking"),
            ],
        },
    }


def build_client_volume_discount_summary(*, customer):
    if customer.default_billing_mode not in {
        customer.DefaultBillingMode.DEFERRED,
        customer.DefaultBillingMode.IMMEDIATE,
    }:
        return None
    from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService

    summary = CustomerVolumeDiscountTierService().get_current_month_summary(customer=customer)
    if summary["current_tier"] is None and summary["next_tier"] is None:
        return None
    return attach_volume_nudge(summary)


def build_client_volume_discount_chart(summary: dict | None) -> dict[str, float] | None:
    """Valeurs sérialisables de la jauge du palier mensuel."""
    if not summary:
        return None
    volume = Decimal(str(summary.get("monthly_volume_linear_m") or "0"))
    next_tier = summary.get("next_tier")
    target = (
        Decimal(str(next_tier.minimum_monthly_linear_m))
        if next_tier is not None
        else max(volume, Decimal("1"))
    )
    achieved = min(volume, target)
    return {
        "achieved": float(achieved),
        "remaining": float(max(target - achieved, Decimal("0"))),
        "progress": float((achieved / target) * Decimal("100")),
        "target": float(target),
        "volume": float(volume),
    }


def _compact_number(value) -> str:
    number = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    text = f"{number:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def attach_volume_nudge(summary: dict, *, stored_copy: dict | None = None) -> dict:
    """Titre + encouragement selon la progression du palier."""
    current = summary.get("current_tier")
    next_tier = summary.get("next_tier")
    volume = Decimal(str(summary["monthly_volume_linear_m"]))
    remaining = summary.get("remaining_to_next_tier_linear_m")
    audience = "immediate" if summary.get("policy") == "prospective" else "deferred"

    if next_tier is None and current is not None:
        percent = _compact_number(current.discount_percent)
        headline = f"Palier max : -{percent} %"
        stage = "max"
    elif next_tier is not None:
        remaining_label = _compact_number(remaining)
        next_percent = _compact_number(next_tier.discount_percent)
        threshold = _compact_number(next_tier.minimum_monthly_linear_m)
        ratio = (
            volume / next_tier.minimum_monthly_linear_m
            if next_tier.minimum_monthly_linear_m
            else Decimal("0")
        )
        if volume <= 0:
            headline = f"Encore {remaining_label} m pour -{next_percent} %"
            stage = "start"
        elif current is not None:
            current_percent = _compact_number(current.discount_percent)
            headline = (
                f"-{current_percent} % en poche · encore {remaining_label} m pour -{next_percent} %"
            )
            stage = "hot" if ratio >= Decimal("0.75") else "hold"
        elif ratio >= Decimal("0.75"):
            headline = f"Plus que {remaining_label} m pour -{next_percent} %"
            stage = "hot"
        else:
            headline = f"{_compact_number(volume)} m au compteur · palier à {threshold} m"
            stage = "warm"
    else:
        return summary

    tokens = {
        "remaining_m": _compact_number(remaining) if remaining is not None else "",
        "next_percent": (
            _compact_number(next_tier.discount_percent) if next_tier is not None else ""
        ),
        "current_percent": (
            _compact_number(current.discount_percent) if current is not None else ""
        ),
        "volume_m": _compact_number(volume),
        "threshold_m": (
            _compact_number(next_tier.minimum_monthly_linear_m) if next_tier is not None else ""
        ),
    }
    copy_source = stored_copy
    if copy_source is None:
        from apps.customers.services.volume_nudge_copy import VolumeDiscountDashboardCopyService

        copy_source = VolumeDiscountDashboardCopyService().stored_messages()
    message = render_nudge_message(
        stage=stage,
        audience=audience,
        tokens=tokens,
        stored=copy_source,
    )

    return {
        **summary,
        "nudge_headline": headline,
        "nudge_message": message,
        "nudge_stage": stage,
        "volume_label": _compact_number(volume),
    }


def _project_focus(*, customer, project) -> dict[str, str]:
    return {
        "label": "Commande à reprendre",
        "title": project.project_number,
        "detail": project.get_status_display(),
        "action_label": "Reprendre",
        "action_url": reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        "tone": "is-attention",
        "kind": "resume",
        "project_public_id": str(project.public_id),
    }


def _order_title(order) -> str:
    return order_client_reference(order) or order_business_number(order) or "Commande"


def _order_url(*, customer, order, query: str = "") -> str:
    url = reverse(
        "portal:client-order-detail",
        kwargs={
            "customer_public_id": customer.public_id,
            "order_public_id": order.public_id,
        },
    )
    return f"{url}{query}"


def build_client_dashboard_focus(
    *, customer, recent_projects, recent_orders, new_order_url: str
) -> dict[str, str]:
    actionable_project = next(
        (project for project in recent_projects if project.status in ACTIONABLE_PROJECT_STATUSES),
        None,
    )
    if actionable_project is not None:
        return _project_focus(customer=customer, project=actionable_project)

    payment_order = next(
        (order for order in recent_orders if getattr(order, "awaits_client_payment", False)),
        None,
    )
    if payment_order is not None:
        return {
            "label": "Action nécessaire",
            "title": _order_title(payment_order),
            "detail": "Paiement à finaliser",
            "action_label": "Payer",
            "action_url": _order_url(
                customer=customer,
                order=payment_order,
                query="?panel=billing&pay=1",
            ),
            "tone": "is-danger",
            "kind": "pay",
            "order_public_id": str(payment_order.public_id),
        }

    for order in recent_orders:
        try:
            shipment = order.shipment
        except ObjectDoesNotExist:
            shipment = None
        tracking_number = str(getattr(shipment, "tracking_number", "") or "").strip()
        if tracking_number:
            return {
                "label": "Expédition à suivre",
                "title": _order_title(order),
                "detail": f"Suivi n° {tracking_number}",
                "action_label": "Suivre",
                "action_url": _order_url(
                    customer=customer,
                    order=order,
                    query="?panel=shipping",
                ),
                "tone": "is-ready",
                "kind": "track",
                "order_public_id": str(order.public_id),
            }

    if recent_projects:
        project = recent_projects[0]
        return {
            **_project_focus(customer=customer, project=project),
            "label": "Commande en cours",
            "action_label": "Consulter",
            "tone": "",
            "kind": "open",
        }

    if recent_orders:
        order = recent_orders[0]
        return {
            "label": "Dernière commande",
            "title": _order_title(order),
            "detail": status_label(order.status),
            "action_label": "Ouvrir",
            "action_url": _order_url(customer=customer, order=order),
            "tone": "",
            "kind": "open",
            "order_public_id": str(order.public_id),
        }

    return {
        "label": "Nouveau projet",
        "title": "Préparer une commande DTF",
        "detail": "Importez vos visuels et configurez votre production.",
        "action_label": "Commencer",
        "action_url": new_order_url,
        "tone": "",
        "kind": "start",
    }


def split_dashboard_lists(*, focus, recent_projects, recent_orders):
    """La carte d’action porte l’item prioritaire ; les listes montrent le reste."""
    if not focus:
        return recent_projects, recent_orders
    project_id = focus.get("project_public_id")
    order_id = focus.get("order_public_id")
    if project_id:
        recent_projects = [
            project for project in recent_projects if str(project.public_id) != str(project_id)
        ]
    if order_id:
        recent_orders = [order for order in recent_orders if str(order.public_id) != str(order_id)]
    return recent_projects, recent_orders


def assemble_client_dashboard(
    *, customer, order_service, project_service, selected_membership=None
):
    empty = {
        "recent_orders": [],
        "recent_projects": [],
        "orders_count": 0,
        "awaits_payment_count": 0,
        "projects_in_progress_count": 0,
        "new_order_url": "",
        "project_feature_enabled": False,
        "client_focus": None,
        "volume_discount_summary": None,
        "financial_dashboard": None,
        "operational_dashboard": None,
        "can_view_financial_dashboard": False,
    }
    if customer is None:
        return empty

    from apps.b2b_order_projects.permissions import (
        b2b_order_projects_enabled_for_customer,
        client_new_order_url,
    )
    from apps.billing.services.production_payment_gate import (
        attach_awaits_client_payment,
        count_orders_awaiting_client_payment,
    )

    orders_qs = order_service.list_customer_orders(customer)
    recent_orders = attach_awaits_client_payment(list(orders_qs[:5]))
    project_feature_enabled = b2b_order_projects_enabled_for_customer(customer)
    recent_projects = []
    projects_in_progress_count = 0
    if project_feature_enabled:
        projects_qs = project_service.list_customer_projects_in_progress(customer)
        recent_projects = project_service.attach_can_delete(list(projects_qs[:5]))
        projects_in_progress_count = projects_qs.count()
        new_order_url = client_new_order_url(customer=customer)
    else:
        new_order_url = reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": customer.public_id},
        )
    client_focus = build_client_dashboard_focus(
        customer=customer,
        recent_projects=recent_projects,
        recent_orders=recent_orders,
        new_order_url=new_order_url,
    )
    operational_dashboard = build_client_operational_dashboard(
        customer=customer,
        projects_in_progress_count=projects_in_progress_count,
    )
    can_view_financial_dashboard = can_view_client_financial_dashboard(selected_membership)
    volume_discount_summary = build_client_volume_discount_summary(customer=customer)
    return {
        "recent_orders": recent_orders,
        "recent_projects": recent_projects,
        "orders_count": orders_qs.count(),
        "awaits_payment_count": count_orders_awaiting_client_payment(customer),
        "projects_in_progress_count": projects_in_progress_count,
        "new_order_url": new_order_url,
        "project_feature_enabled": project_feature_enabled,
        "client_focus": client_focus,
        "volume_discount_summary": volume_discount_summary,
        "volume_discount_chart": build_client_volume_discount_chart(volume_discount_summary),
        "financial_dashboard": (
            build_client_financial_dashboard(customer=customer)
            if can_view_financial_dashboard
            else None
        ),
        "operational_dashboard": operational_dashboard,
        "can_view_financial_dashboard": can_view_financial_dashboard,
    }
