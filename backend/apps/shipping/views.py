from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasStaffShipmentCreateAccess, HasStaffShipmentReadAccess
from apps.customers.permissions import HasScopedCustomerAccess
from apps.shipping.services.sendcloud import ShipmentService

shipment_service = ShipmentService()


def raise_api_validation_error(error: DjangoValidationError):
    if hasattr(error, "message_dict"):
        raise DRFValidationError(error.message_dict)
    raise DRFValidationError({"detail": error.messages})


def serialize_shipment(shipment) -> dict[str, object]:
    return {
        "public_id": str(shipment.public_id),
        "order_public_id": str(shipment.order.public_id),
        "customer": {
            "public_id": str(shipment.order.customer.public_id),
            "name": shipment.order.customer.name,
        },
        "status": shipment.status,
        "shipping_option_code": shipment.shipping_option_code,
        "contract_id": shipment.contract_id,
        "tracking_number": shipment.tracking_number,
        "tracking_url": shipment.tracking_url,
        "sendcloud_status": {
            "code": shipment.sendcloud_status_code,
            "message": shipment.sendcloud_status_message,
        },
        "label": {
            "has_file": bool(shipment.label_file),
            "filename": shipment.label_filename,
            "mime_type": shipment.label_mime_type,
            "retrieved_at": shipment.label_retrieved_at.isoformat()
            if shipment.label_retrieved_at
            else None,
        },
        "last_error_message": shipment.last_error_message,
        "last_api_sync_at": shipment.last_api_sync_at.isoformat()
        if shipment.last_api_sync_at
        else None,
        "request_snapshot": shipment.request_snapshot,
        "created_at": shipment.created_at.isoformat(),
        "updated_at": shipment.updated_at.isoformat(),
    }


def serialize_customer_shipment(snapshot: dict[str, object] | None) -> dict[str, object] | None:
    if snapshot is None:
        return None
    return {
        "public_id": snapshot["public_id"],
        "status": snapshot["status"],
        "tracking_number": snapshot["tracking_number"],
        "tracking_url": snapshot["tracking_url"],
        "carrier_status": snapshot["carrier_status"],
        "last_sync_at": snapshot["last_sync_at"],
    }


class ClientShipmentDetailView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id):
        snapshot = shipment_service.get_customer_shipment_snapshot(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if snapshot is None:
            raise Http404
        return Response(serialize_customer_shipment(snapshot))


class StaffShipmentSyncTrackingView(APIView):
    permission_classes = [IsAuthenticated, HasStaffShipmentReadAccess]

    def post(self, request, order_public_id):
        try:
            _order, shipment = shipment_service.sync_shipment_tracking_from_sendcloud(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)
        if shipment is None:
            raise Http404
        return Response(serialize_shipment(shipment))


class StaffShipmentDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffShipmentReadAccess]

    def get(self, request, order_public_id):
        _order, shipment = shipment_service.get_staff_shipment(
            order_public_id=order_public_id,
            actor=request.user,
            source="staff_api",
        )
        if shipment is None:
            raise Http404
        return Response(serialize_shipment(shipment))


class StaffShipmentCreateView(APIView):
    permission_classes = [IsAuthenticated, HasStaffShipmentCreateAccess]

    def post(self, request, order_public_id):
        try:
            _order, shipment = shipment_service.create_shipment(
                order_public_id=order_public_id,
                actor=request.user,
                source="staff_api",
                payload=request.data,
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        if shipment is None:
            raise Http404
        return Response(serialize_shipment(shipment), status=201)
