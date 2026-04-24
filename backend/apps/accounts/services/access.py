from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from apps.customers.models import Customer, CustomerMembership


@dataclass(frozen=True)
class MembershipScope:
    membership_public_id: UUID
    customer_public_id: UUID
    customer_name: str
    role: str

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "membership_public_id": str(self.membership_public_id),
            "customer_public_id": str(self.customer_public_id),
            "customer_name": self.customer_name,
            "role": self.role,
            "is_owner": self.role == CustomerMembership.Role.OWNER,
        }


@dataclass(frozen=True)
class UserScope:
    is_authenticated: bool
    is_staff: bool
    has_staff_portal_access: bool
    memberships: tuple[MembershipScope, ...]

    @property
    def customer_public_ids(self) -> tuple[str, ...]:
        return tuple(str(membership.customer_public_id) for membership in self.memberships)

    def to_dict(self) -> dict[str, object]:
        return {
            "is_authenticated": self.is_authenticated,
            "is_staff": self.is_staff,
            "has_staff_portal_access": self.has_staff_portal_access,
            "customer_public_ids": list(self.customer_public_ids),
        }


class AccessScopeService:
    staff_portal_permission = "accounts.access_staff_portal"

    def get_customer_queryset(self, user):
        return Customer.objects.for_user(user)

    def get_membership_queryset(self, user):
        if not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
            return CustomerMembership.objects.none()
        return CustomerMembership.objects.active().for_user(user).select_related("customer")

    def get_user_scope(self, user) -> UserScope:
        memberships = tuple(
            MembershipScope(
                membership_public_id=membership.public_id,
                customer_public_id=membership.customer.public_id,
                customer_name=membership.customer.name,
                role=membership.role,
            )
            for membership in self.get_membership_queryset(user)
        )
        return UserScope(
            is_authenticated=getattr(user, "is_authenticated", False),
            is_staff=bool(getattr(user, "is_staff", False)),
            has_staff_portal_access=self.can_access_staff_portal(user),
            memberships=memberships,
        )

    def get_customer_membership(
        self, user, customer_public_id: UUID | str
    ) -> CustomerMembership | None:
        return (
            self.get_membership_queryset(user)
            .filter(customer__public_id=customer_public_id)
            .first()
        )

    def get_customer_membership_for_customer(self, user, customer) -> CustomerMembership | None:
        if customer is None:
            return None
        return self.get_membership_queryset(user).filter(customer=customer).first()

    def can_access_customer(self, user, customer_public_id: UUID | str) -> bool:
        return self.get_customer_membership(user, customer_public_id) is not None

    def can_manage_customer(self, user, customer_public_id: UUID | str) -> bool:
        membership = self.get_customer_membership(user, customer_public_id)
        return membership is not None and membership.is_owner

    def can_access_staff_portal(self, user) -> bool:
        return bool(
            getattr(user, "is_authenticated", False)
            and getattr(user, "is_active", False)
            and getattr(user, "is_staff", False)
            and user.has_perm(self.staff_portal_permission)
        )

    def can_access_staff_domain(self, user, permission: str) -> bool:
        return bool(self.can_access_staff_portal(user) and user.has_perm(permission))
