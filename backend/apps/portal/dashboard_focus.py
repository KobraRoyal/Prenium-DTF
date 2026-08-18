from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.urls import reverse

from apps.b2b_order_projects.models import B2BOrderProject
from apps.core.public_refs import short_public_ref
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


def format_linear_m(value) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if amount == amount.to_integral_value():
        return f"{int(amount)} m"
    return f"{amount.normalize()} m".replace(".", ",")


def format_percent(value) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount == amount.to_integral_value():
        return f"{int(amount)} %"
    return f"{amount.normalize()} %".replace(".", ",")


def format_money(value, *, currency: str = "EUR") -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    formatted = f"{amount:.2f}".replace(".", ",")
    suffix = "€" if currency == "EUR" else currency
    return f"{formatted} {suffix}"


def exclude_focused_item(*, items, public_id):
    if not public_id:
        return list(items)
    focused = str(public_id)
    return [item for item in items if str(item.public_id) != focused]


def _current_month_bounds():
    from datetime import datetime, time

    from django.utils import timezone

    month_start = timezone.localdate().replace(day=1)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    current_tz = timezone.get_current_timezone()
    starts_at = timezone.make_aware(datetime.combine(month_start, time.min), current_tz)
    ends_at = timezone.make_aware(datetime.combine(next_month, time.min), current_tz)
    return month_start, starts_at, ends_at


def build_client_account_snapshot(*, customer) -> dict[str, object]:
    from django.db.models import Sum

    from apps.orders.models import Order

    month_start, starts_at, ends_at = _current_month_bounds()
    deferred = customer.default_billing_mode == customer.DefaultBillingMode.DEFERRED
    if deferred:
        priced_orders = Order.objects.filter(
            customer=customer,
            billing_mode=Order.BillingMode.DEFERRED,
            pricing_status=Order.PricingStatus.PRICED,
            billing_statement__isnull=True,
        ).exclude(status=Order.Status.DRAFT)
        period_label = "encours non relevé"
    else:
        priced_orders = Order.objects.filter(
            customer=customer,
            pricing_status=Order.PricingStatus.PRICED,
            created_at__gte=starts_at,
            created_at__lt=ends_at,
        ).exclude(status__in=[Order.Status.CANCELLED, Order.Status.DRAFT])
        period_label = None
    ca_ht = priced_orders.aggregate(total=Sum("subtotal_amount"))["total"] or Decimal("0.00")
    ca_ht = ca_ht.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "month": month_start,
        "period_label": period_label,
        "ca_ht": ca_ht,
        "ca_ht_label": format_money(ca_ht),
        "priced_order_count": priced_orders.count(),
        "show_open_balance": False,
        "currency": "EUR",
    }


def build_client_volume_discount_summary(*, customer):
    if customer.default_billing_mode != customer.DefaultBillingMode.DEFERRED:
        return None
    from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService

    summary = CustomerVolumeDiscountTierService().get_current_month_summary(customer=customer)
    if summary["current_tier"] is None and summary["next_tier"] is None:
        return None
    monthly_volume = summary["monthly_volume_linear_m"]
    summary["progress_value"] = f"{monthly_volume:f}"
    summary["progress_max"] = (
        f"{summary['next_tier'].minimum_monthly_linear_m:f}" if summary["next_tier"] else None
    )
    summary["volume_label"] = format_linear_m(monthly_volume)
    summary["remaining_label"] = (
        format_linear_m(summary["remaining_to_next_tier_linear_m"])
        if summary["next_tier"]
        else None
    )
    summary["next_threshold_label"] = (
        format_linear_m(summary["next_tier"].minimum_monthly_linear_m)
        if summary["next_tier"]
        else None
    )
    summary["current_percent_label"] = (
        format_percent(summary["current_tier"].discount_percent)
        if summary["current_tier"]
        else "0 %"
    )
    summary["next_percent_label"] = (
        format_percent(summary["next_tier"].discount_percent) if summary["next_tier"] else None
    )
    summary["show_savings"] = bool(
        summary["current_tier"] and summary["discount_amount"] and summary["discount_amount"] > 0
    )
    return summary


def project_action_label(status) -> str:
    return _project_action(status)[1]


def attach_project_dashboard_verbs(projects):
    for project in projects:
        project.dashboard_verb = project_action_label(project.status)
    return projects


def _project_action(status) -> tuple[str, str]:
    if status in {
        B2BOrderProject.Status.DRAFT,
        B2BOrderProject.Status.INCOMPLETE,
    }:
        return "Commande à reprendre", "Compléter"
    if status in {
        B2BOrderProject.Status.ACTION_REQUIRED,
        B2BOrderProject.Status.CHANGES_REQUESTED,
    }:
        return "Action nécessaire", "Corriger"
    if status == B2BOrderProject.Status.READY_TO_SUBMIT:
        return "Prêt à transmettre", "Transmettre"
    if status == B2BOrderProject.Status.PRICE_CONFIRMATION_REQUIRED:
        return "Tarif à confirmer", "Confirmer"
    return "Commande à reprendre", "Reprendre"


def _visual_count_label(count: int) -> str:
    if count == 1:
        return "1 visuel"
    return f"{count} visuels"


def _project_focus(*, customer, project) -> dict[str, str]:
    item_count = len(project.items.all())
    name = str(getattr(project, "name", "") or "").strip()
    title = name or project.project_number
    detail_parts = [_visual_count_label(item_count)]
    if name:
        detail_parts.insert(0, project.project_number)
    label, action_label = _project_action(project.status)
    return {
        "label": label,
        "title": title,
        "heading": f"{action_label} · {title}",
        "detail": " · ".join(detail_parts),
        "action_label": action_label,
        "action_url": reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        "tone": "is-attention",
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


def _order_focus(
    *, customer, order, label, detail, action_label, tone, query: str = ""
) -> dict[str, str]:
    return {
        "label": label,
        "title": _order_title(order),
        "heading": f"{action_label} · {_order_title(order)}",
        "detail": detail,
        "action_label": action_label,
        "action_url": _order_url(customer=customer, order=order, query=query),
        "tone": tone,
        "order_public_id": str(order.public_id),
    }


def build_client_dashboard_focus(
    *,
    customer,
    recent_projects,
    recent_orders,
    new_order_url: str,
    can_view_account_finance: bool = True,
    can_create_orders: bool = True,
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
    if can_view_account_finance and payment_order is not None:
        return _order_focus(
            customer=customer,
            order=payment_order,
            label="Action nécessaire",
            detail="Paiement non finalisé",
            action_label="Payer",
            tone="is-danger",
            query="?panel=billing&pay=1",
        )

    for order in recent_orders:
        try:
            shipment = order.shipment
        except ObjectDoesNotExist:
            shipment = None
        tracking_number = str(getattr(shipment, "tracking_number", "") or "").strip()
        if tracking_number:
            return _order_focus(
                customer=customer,
                order=order,
                label="Expédition à suivre",
                detail=f"Suivi n° {tracking_number}",
                action_label="Suivre",
                tone="is-ready",
                query="?panel=shipping",
            )

    if recent_projects:
        project = recent_projects[0]
        return {
            **_project_focus(customer=customer, project=project),
            "label": "Commande en cours",
            "action_label": "Consulter",
            "heading": f"Consulter · {project.name or project.project_number}",
            "tone": "",
        }

    if recent_orders:
        order = recent_orders[0]
        return _order_focus(
            customer=customer,
            order=order,
            label="Dernière commande",
            detail=status_label(order.status),
            action_label="Ouvrir",
            tone="",
        )

    if not can_create_orders:
        return {
            "label": "Suivi",
            "title": "Aucune commande à suivre",
            "heading": "Suivi des commandes",
            "detail": "Les commandes transmises par votre atelier apparaîtront ici.",
            "action_label": "Voir les commandes",
            "action_url": reverse(
                "portal:client-order-list",
                kwargs={"customer_public_id": customer.public_id},
            ),
            "tone": "",
        }

    return {
        "label": "Nouveau projet",
        "title": "Préparer une commande DTF",
        "heading": "Préparer une commande DTF",
        "detail": "Importez vos visuels et configurez votre production.",
        "action_label": "Commencer",
        "action_url": new_order_url,
        "tone": "",
    }
