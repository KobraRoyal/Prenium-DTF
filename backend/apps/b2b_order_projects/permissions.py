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
