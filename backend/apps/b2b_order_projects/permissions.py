from django.conf import settings
from rest_framework.permissions import BasePermission

from apps.accounts.services.access import AccessScopeService

access_scope_service = AccessScopeService()


def b2b_order_projects_enabled_for_customer(customer) -> bool:
    return bool(
        getattr(settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False)
        and customer is not None
        and customer.is_active
    )


def customer_requires_gang_sheet_orders(customer) -> bool:
    """Comptant CB : commande uniquement via Gang Sheet (métrage / prix auto)."""
    from apps.customers.models import Customer

    return bool(
        customer is not None
        and getattr(customer, "default_billing_mode", None) == Customer.DefaultBillingMode.IMMEDIATE
    )


def client_new_order_url(*, customer) -> str:
    """URL d’entrée « Nouvelle commande » selon feature projets et mode compte."""
    from django.urls import reverse

    if not b2b_order_projects_enabled_for_customer(customer):
        return reverse(
            "portal:client-checkout",
            kwargs={"customer_public_id": customer.public_id},
        )
    if customer_requires_gang_sheet_orders(customer):
        return reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    return reverse(
        "portal:client-order-project-create",
        kwargs={"customer_public_id": customer.public_id},
    )


class HasB2BOrderProjectFeatureAccess(BasePermission):
    message = "La fonctionnalité de projets de commande B2B n'est pas activée."

    def has_permission(self, request, view) -> bool:
        return b2b_order_projects_enabled_for_customer(getattr(view, "customer", None))


class HasStaffB2BOrderProjectReadAccess(BasePermission):
    message = "Accès OPS aux projets B2B refusé."

    def has_permission(self, request, view) -> bool:
        return bool(
            getattr(settings, "B2B_DTF_ORDER_PROJECT_ENABLED", False)
            and access_scope_service.can_access_staff_domain(
                request.user, "b2b_order_projects.view_b2borderproject"
            )
        )
