from __future__ import annotations

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


def build_client_volume_discount_summary(*, customer):
    if customer.default_billing_mode not in {
        customer.DefaultBillingMode.DEFERRED,
        customer.DefaultBillingMode.IMMEDIATE,
    }:
        return None
    from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService

    summary = CustomerVolumeDiscountTierService().get_current_month_summary(customer=customer)
    return (
        summary if summary["current_tier"] is not None or summary["next_tier"] is not None else None
    )


def _project_focus(*, customer, project) -> dict[str, str]:
    item_count = len(project.items.all())
    return {
        "label": "Commande à reprendre",
        "title": project.project_number,
        "detail": f"{item_count} visuel(s) · {project.get_status_display()}",
        "action_label": "Reprendre",
        "action_url": reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        ),
        "tone": "is-attention",
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
            }

    if recent_projects:
        project = recent_projects[0]
        return {
            **_project_focus(customer=customer, project=project),
            "label": "Commande en cours",
            "action_label": "Consulter",
            "tone": "",
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
        }

    return {
        "label": "Nouveau projet",
        "title": "Préparer une commande DTF",
        "detail": "Importez vos visuels et configurez votre production.",
        "action_label": "Commencer",
        "action_url": new_order_url,
        "tone": "",
    }
