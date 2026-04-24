from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customers.permissions import HasCustomerOwnerAccess, HasScopedCustomerAccess

from .permissions import HasCustomerScopeAccess, HasStaffPortalAccess
from .services.access import AccessScopeService


def build_user_payload(user) -> dict[str, object]:
    return {
        "public_id": str(user.public_id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "is_active": user.is_active,
    }


def build_membership_payload(membership) -> dict[str, str | bool]:
    return {
        "membership_public_id": str(membership.public_id),
        "customer_public_id": str(membership.customer.public_id),
        "customer_name": membership.customer.name,
        "role": membership.role,
        "is_active": membership.is_active,
        "is_owner": membership.is_owner,
    }


def build_customer_payload(customer, membership) -> dict[str, object]:
    return {
        "public_id": str(customer.public_id),
        "name": customer.name,
        "billing_email": customer.billing_email,
        "is_active": customer.is_active,
        "membership": build_membership_payload(membership),
    }


class ClientScopeView(APIView):
    permission_classes = [IsAuthenticated, HasCustomerScopeAccess]
    access_scope_service = AccessScopeService()

    def get(self, request):
        scope = getattr(self, "user_scope", self.access_scope_service.get_user_scope(request.user))
        memberships = [membership.to_dict() for membership in scope.memberships]
        return Response(
            {
                "user": build_user_payload(request.user),
                "memberships": memberships,
                "scope": scope.to_dict(),
            }
        )


class ScopedCustomerView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id):
        return Response(
            {"customer": build_customer_payload(self.customer, self.customer_membership)}
        )


class CustomerOwnerView(APIView):
    permission_classes = [IsAuthenticated, HasCustomerOwnerAccess]

    def get(self, request, customer_public_id):
        return Response(
            {
                "customer": build_customer_payload(self.customer, self.customer_membership),
                "allowed_action": "manage_customer_memberships",
            }
        )


class StaffPortalView(APIView):
    permission_classes = [IsAuthenticated, HasStaffPortalAccess]
    access_scope_service = AccessScopeService()

    def get(self, request):
        scope = self.access_scope_service.get_user_scope(request.user)
        return Response(
            {
                "user": build_user_payload(request.user),
                "staff": {
                    "has_staff_portal_access": scope.has_staff_portal_access,
                    "staff_mfa_required": request.user.staff_mfa_required,
                    "staff_mfa_enabled": request.user.staff_mfa_enabled,
                },
            }
        )
