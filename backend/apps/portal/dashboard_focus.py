from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from apps.b2b_order_projects.models import B2BOrderProject
from apps.core.public_refs import short_public_ref
from apps.customers.services.volume_nudge_copy import render_nudge_message
from apps.orders.references import order_client_reference
from apps.portal.views_common import status_label

ACTIONABLE_PROJECT_STATUSES = {
    B2BOrderProject.Status.DRAFT,
    B2BOrderProject.Status.INCOMPLETE,
    B2BOrderProject.Status.ACTION_REQUIRED,
    B2BOrderProject.Status.READY_TO_SUBMIT,
    B2BOrderProject.Status.CHANGES_REQUESTED,
    B2BOrderProject.Status.PRICE_CONFIRMATION_REQUIRED,
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
    return order_client_reference(order) or f"Commande #{short_public_ref(order.public_id)}"


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


def assemble_client_dashboard(*, customer, order_service, project_service):
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
    recent_projects, recent_orders = split_dashboard_lists(
        focus=client_focus,
        recent_projects=recent_projects,
        recent_orders=recent_orders,
    )
    return {
        "recent_orders": recent_orders,
        "recent_projects": recent_projects,
        "orders_count": orders_qs.count(),
        "awaits_payment_count": count_orders_awaiting_client_payment(customer),
        "projects_in_progress_count": projects_in_progress_count,
        "new_order_url": new_order_url,
        "project_feature_enabled": project_feature_enabled,
        "client_focus": client_focus,
        "volume_discount_summary": build_client_volume_discount_summary(customer=customer),
    }
