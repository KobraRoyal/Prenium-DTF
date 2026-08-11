import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import HasStaffShipmentCreateAccess, HasStaffShipmentReadAccess
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.customers.permissions import HasScopedCustomerAccess
from apps.shipping.services.sendcloud import (
    SendcloudAPIError,
    SendcloudConfigurationError,
    ShipmentService,
    build_sendcloud_webhook_identity,
    extract_parcel_from_webhook_payload,
    verify_sendcloud_webhook_signature,
)
from apps.shipping.tasks import process_sendcloud_parcel_status_webhook_task

logger = logging.getLogger(__name__)
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
        "sendcloud_order_id": shipment.sendcloud_order_id,
        "tracking_number": shipment.tracking_number,
        "tracking_url": shipment.tracking_url,
        "sendcloud_status": {
            "code": shipment.sendcloud_status_code,
            "message": shipment.sendcloud_status_message,
        },
        "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
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
        "shipped_at": snapshot.get("shipped_at"),
        "last_sync_at": snapshot["last_sync_at"],
    }


def build_label_download_response(shipment):
    response = FileResponse(
        shipment.label_file.open("rb"),
        as_attachment=True,
        filename=shipment.label_filename or "sendcloud-label.pdf",
        content_type=shipment.label_mime_type or "application/pdf",
    )
    try:
        response["Content-Length"] = str(shipment.label_file.size)
    except Exception:  # noqa: BLE001 - size may be unavailable on some storages
        pass
    return response


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


class StaffShipmentLabelDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasStaffShipmentReadAccess]

    def get(self, request, order_public_id):
        _order, shipment = shipment_service.download_staff_shipment_label(
            order_public_id=order_public_id,
            actor=request.user,
            source="staff_api",
        )
        if shipment is None:
            raise Http404
        return build_label_download_response(shipment)


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


class BackendSendcloudWebhookView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request):
        payload = request.body
        signature = request.headers.get("Sendcloud-Signature", "")
        try:
            verify_sendcloud_webhook_signature(payload=payload, signature_header=signature)
        except (SendcloudAPIError, SendcloudConfigurationError) as exc:
            logger.warning("sendcloud_webhook_rejected", extra={"reason": str(exc)})
            record_event(
                action="security.sendcloud_webhook_rejected",
                status=AuditLogEntry.Status.FAILURE,
                message=str(exc)[:255],
                metadata={"path": request.path},
            )
            raise PermissionDenied("Invalid Sendcloud webhook.") from exc

        try:
            parcel = extract_parcel_from_webhook_payload(payload)
            event_identity = build_sendcloud_webhook_identity(payload)
        except SendcloudAPIError as exc:
            record_event(
                action="shipping.sendcloud_webhook_invalid_payload",
                status=AuditLogEntry.Status.FAILURE,
                message=str(exc)[:255],
                metadata={"path": request.path},
            )
            raise DRFValidationError({"detail": str(exc)}) from exc

        try:
            process_sendcloud_parcel_status_webhook_task.delay(
                parcel=parcel,
                event_key=event_identity.event_key,
                payload_hash=event_identity.payload_hash,
                provider_event_id=event_identity.provider_event_id,
            )
        except Exception as exc:  # noqa: BLE001 - broker failures must trigger a provider retry
            logger.error(
                "sendcloud_webhook_queue_failed",
                extra={"error_type": type(exc).__name__},
            )
            record_event(
                action="shipping.sendcloud_webhook_queue_failed",
                status=AuditLogEntry.Status.FAILURE,
                message="Sendcloud webhook could not be queued.",
                metadata={
                    "error_type": type(exc).__name__,
                    "provider_event_id": event_identity.provider_event_id,
                    "payload_hash": event_identity.payload_hash,
                    "path": request.path,
                },
            )
            return Response({"received": False, "queued": False}, status=503)

        return Response({"received": True, "queued": True}, status=202)
