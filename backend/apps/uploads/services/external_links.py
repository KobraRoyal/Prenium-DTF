from django.core.exceptions import PermissionDenied
from django.http import Http404

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.services import record_event
from apps.orders.models import Order
from apps.uploads.models import OrderUpload
from apps.uploads.validators import validate_external_url


class ExternalUploadLinkService:
    def open_link(self, *, actor, order_public_id, upload_public_id, customer=None):
        access = AccessScopeService()
        if customer is not None:
            if access.get_customer_membership_for_customer(actor, customer) is None:
                raise PermissionDenied
            orders = Order.objects.for_customer(customer)
            audience = "client"
        else:
            if not all(
                access.can_access_staff_domain(actor, permission)
                for permission in ("orders.view_order", "uploads.view_orderupload")
            ):
                raise PermissionDenied
            orders = Order.objects.all()
            audience = "staff"
        upload = (
            OrderUpload.objects.select_related("order__customer")
            .filter(order__in=orders.filter(public_id=order_public_id), public_id=upload_public_id)
            .first()
        )
        if upload is None or not upload.is_external:
            raise Http404
        destination = validate_external_url(upload.external_url)
        record_event(
            action="order_upload.external_link_opened",
            actor=actor,
            target=upload,
            metadata={
                "order_public_id": str(upload.order.public_id),
                "customer_public_id": str(upload.order.customer.public_id),
                "audience": audience,
            },
        )
        return destination
