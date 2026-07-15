from rest_framework.permissions import BasePermission

from apps.accounts.services.access import AccessScopeService
from apps.customers.models import CustomerMembership

access_scope_service = AccessScopeService()


class BaseCustomerMembershipPermission(BasePermission):
    required_role = None
    message = "Customer access denied."

    def has_permission(self, request, view) -> bool:
        customer_public_id = view.kwargs.get("customer_public_id")
        if customer_public_id is None:
            return False

        membership = access_scope_service.get_customer_membership(request.user, customer_public_id)
        if membership is None:
            return False

        if self.required_role is not None and membership.role != self.required_role:
            return False

        view.customer_membership = membership
        view.customer = membership.customer
        return True


class HasScopedCustomerAccess(BaseCustomerMembershipPermission):
    pass


class HasCustomerOwnerAccess(BaseCustomerMembershipPermission):
    required_role = CustomerMembership.Role.OWNER


class HasCustomerTeamManagerAccess(BaseCustomerMembershipPermission):
    def has_permission(self, request, view) -> bool:
        if not super().has_permission(request, view):
            return False
        return view.customer_membership.can_manage_team
