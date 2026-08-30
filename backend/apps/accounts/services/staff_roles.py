from __future__ import annotations

from django.contrib.auth.models import Permission

from apps.accounts.models import StaffMembership

_STAFF_PORTAL = "accounts.access_staff_portal"
_MANAGE_TEAM = "accounts.manage_staff_team"

_READONLY_PERMISSIONS = (
    _STAFF_PORTAL,
    "orders.view_order",
    "customers.view_customer",
    "uploads.view_orderupload",
    "uploads.view_orderuploadinspection",
    "production.view_productionjob",
    "shipping.view_shipment",
    "billing.view_payment",
    "billing.view_invoice",
    "prospects.view_prospectprofile",
)

_MEMBER_PERMISSIONS = (
    *_READONLY_PERMISSIONS,
    "uploads.review_orderupload",
    "production.scan_productionjob",
)

_ADMIN_PERMISSIONS = (
    _STAFF_PORTAL,
    _MANAGE_TEAM,
    "notifications.view_emailtemplate",
    "notifications.change_emailtemplate",
    "catalog.view_catalogservice",
    "customers.view_customer",
    "customers.change_customer",
    "customers.manage_customer_pricing",
    "prospects.view_prospectprofile",
    "prospects.review_prospectprofile",
    "orders.view_order",
    "orders.change_order",
    "orders.delete_atelier_order",
    "uploads.view_orderupload",
    "uploads.view_orderuploadinspection",
    "uploads.review_orderupload",
    "uploads.view_orderuploaddrivesync",
    "gang_sheets.view_gangsheet",
    "gang_sheets.configure_gangsheet",
    "gang_sheets.download_final_gangsheet",
    "production.view_productionjob",
    "production.transition_productionjob",
    "production.scan_productionjob",
    "production.scan_transition_productionjob",
    "production.view_productionmachine",
    "production.manage_productionmachine",
    "production.assign_productionmachine",
    "production.confirm_productionprint",
    "shipping.view_shipment",
    "shipping.create_shipment",
    "billing.view_payment",
    "billing.view_invoice",
    "billing.mark_invoice_paid",
    "billing.view_billingstatement",
    "billing.add_billingstatement",
    "pod.access_pod_atelier",
    "pod.manage_pod_catalog",
    "inventory.manage_warehouse",
)

_ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    StaffMembership.Role.OWNER: _ADMIN_PERMISSIONS,
    StaffMembership.Role.ADMIN: _ADMIN_PERMISSIONS,
    StaffMembership.Role.MEMBER: _MEMBER_PERMISSIONS,
    StaffMembership.Role.READONLY: _READONLY_PERMISSIONS,
}


def permission_codenames_for_role(role: str) -> tuple[str, ...]:
    if role not in _ROLE_PERMISSIONS:
        raise ValueError(f"Unknown staff role: {role}")
    return _ROLE_PERMISSIONS[role]


def sync_staff_access(*, user, role: str, is_active: bool) -> None:
    """Applique le rôle Atelier sur le compte utilisateur (hors superuser)."""
    if getattr(user, "is_superuser", False):
        user.is_staff = True
        user.save(update_fields=("is_staff", "updated_at"))
        return

    if not is_active:
        user.is_staff = False
        user.user_permissions.clear()
        user.save(update_fields=("is_staff", "updated_at"))
        return

    permissions = []
    for name in permission_codenames_for_role(role):
        app_label, codename = name.split(".", 1)
        permission = Permission.objects.filter(
            codename=codename,
            content_type__app_label=app_label,
        ).first()
        if permission is not None:
            permissions.append(permission)

    user.is_staff = True
    user.user_permissions.set(permissions)
    user.save(update_fields=("is_staff", "updated_at"))
