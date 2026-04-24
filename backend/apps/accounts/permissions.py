from rest_framework.permissions import BasePermission

from .services.access import AccessScopeService

access_scope_service = AccessScopeService()


class HasCustomerScopeAccess(BasePermission):
    message = "An active customer membership is required."

    def has_permission(self, request, view) -> bool:
        scope = access_scope_service.get_user_scope(request.user)
        view.user_scope = scope
        return bool(scope.memberships)


class HasStaffPortalAccess(BasePermission):
    message = "Staff portal access denied."

    def has_permission(self, request, view) -> bool:
        return access_scope_service.can_access_staff_portal(request.user)


class BaseStaffDomainAccess(BasePermission):
    required_permission = ""
    message = "Staff domain access denied."

    def has_permission(self, request, view) -> bool:
        if not self.required_permission:
            return False
        return access_scope_service.can_access_staff_domain(
            request.user, self.required_permission
        )


class HasStaffCatalogReadAccess(BaseStaffDomainAccess):
    required_permission = "catalog.view_catalogservice"
    message = "Staff catalog access denied."


class HasStaffOrderReadAccess(BaseStaffDomainAccess):
    required_permission = "orders.view_order"
    message = "Staff order access denied."


class HasStaffOrderUploadReadAccess(BaseStaffDomainAccess):
    required_permission = "uploads.view_orderupload"
    message = "Staff order upload access denied."


class HasStaffOrderUploadInspectionReadAccess(BaseStaffDomainAccess):
    required_permission = "uploads.view_orderuploadinspection"
    message = "Staff order upload inspection access denied."


class HasStaffOrderUploadDriveSyncReadAccess(BaseStaffDomainAccess):
    required_permission = "uploads.view_orderuploaddrivesync"
    message = "Staff order upload drive sync access denied."


class HasStaffProductionWorkflowReadAccess(BaseStaffDomainAccess):
    required_permission = "production.view_productionjob"
    message = "Staff production workflow access denied."


class HasStaffProductionWorkflowTransitionAccess(BaseStaffDomainAccess):
    required_permission = "production.transition_productionjob"
    message = "Staff production transition access denied."


class HasStaffProductionReadAccess(HasStaffProductionWorkflowReadAccess):
    pass


class HasStaffProductionTransitionAccess(HasStaffProductionWorkflowTransitionAccess):
    pass


class HasStaffProductionScanResolveAccess(BasePermission):
    message = "Staff production scan access denied."

    def has_permission(self, request, view) -> bool:
        return bool(
            access_scope_service.can_access_staff_domain(
                request.user, "production.view_productionjob"
            )
            and access_scope_service.can_access_staff_domain(
                request.user, "production.scan_productionjob"
            )
        )


class HasStaffProductionScanTransitionAccess(BasePermission):
    message = "Staff production scan transition access denied."

    def has_permission(self, request, view) -> bool:
        return bool(
            access_scope_service.can_access_staff_domain(
                request.user, "production.transition_productionjob"
            )
            and access_scope_service.can_access_staff_domain(
                request.user, "production.scan_transition_productionjob"
            )
        )


class HasStaffShipmentReadAccess(BaseStaffDomainAccess):
    required_permission = "shipping.view_shipment"
    message = "Staff shipment access denied."


class HasStaffShipmentCreateAccess(BasePermission):
    message = "Staff shipment creation access denied."

    def has_permission(self, request, view) -> bool:
        return bool(
            access_scope_service.can_access_staff_domain(
                request.user, "shipping.view_shipment"
            )
            and access_scope_service.can_access_staff_domain(
                request.user, "shipping.create_shipment"
            )
        )


class HasStaffBillingReadAccess(BasePermission):
    message = "Staff billing access denied."

    def has_permission(self, request, view) -> bool:
        return bool(
            access_scope_service.can_access_staff_domain(
                request.user, "billing.view_payment"
            )
            and access_scope_service.can_access_staff_domain(
                request.user, "billing.view_invoice"
            )
        )
