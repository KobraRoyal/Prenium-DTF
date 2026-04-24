from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import (
    HasStaffOrderUploadDriveSyncReadAccess,
    HasStaffOrderUploadInspectionReadAccess,
    HasStaffOrderUploadReadAccess,
)
from apps.customers.permissions import HasScopedCustomerAccess
from apps.uploads.services.uploads import OrderUploadService

upload_service = OrderUploadService()


def serialize_order_upload(order_upload, *, include_customer: bool) -> dict[str, object]:
    payload = {
        "public_id": str(order_upload.public_id),
        "order_public_id": str(order_upload.order.public_id),
        "original_filename": order_upload.original_filename,
        "mime_type": order_upload.mime_type,
        "size_bytes": order_upload.size_bytes,
        "uploaded_at": order_upload.created_at.isoformat(),
    }
    if include_customer:
        payload["customer"] = {
            "public_id": str(order_upload.order.customer.public_id),
            "name": order_upload.order.customer.name,
        }
    return payload


def serialize_order_upload_inspection(
    inspection,
    *,
    order_upload,
    include_customer: bool,
) -> dict[str, object]:
    payload = {
        "public_id": str(inspection.public_id),
        "upload_public_id": str(order_upload.public_id),
        "order_public_id": str(order_upload.order.public_id),
        "status": inspection.status,
        "summary_message": inspection.summary_message,
        "file_kind": inspection.file_kind,
        "file_extension": inspection.file_extension,
        "image_width": inspection.image_width,
        "image_height": inspection.image_height,
        "checked_at": inspection.checked_at.isoformat() if inspection.checked_at else None,
        "file": {
            "original_filename": order_upload.original_filename,
            "mime_type": order_upload.mime_type,
            "size_bytes": order_upload.size_bytes,
        },
        "metadata": inspection.metadata,
    }
    if include_customer:
        payload["customer"] = {
            "public_id": str(order_upload.order.customer.public_id),
            "name": order_upload.order.customer.name,
        }
    return payload


def serialize_order_upload_drive_sync(
    sync,
    *,
    order_upload,
    include_customer: bool = False,
) -> dict[str, object]:
    payload = {
        "public_id": str(sync.public_id),
        "upload_public_id": str(order_upload.public_id),
        "order_public_id": str(order_upload.order.public_id),
        "status": sync.status,
        "last_error": sync.last_error,
        "last_attempt_at": sync.last_attempt_at.isoformat() if sync.last_attempt_at else None,
        "synced_at": sync.synced_at.isoformat() if sync.synced_at else None,
        "file": {
            "original_filename": order_upload.original_filename,
            "mime_type": order_upload.mime_type,
            "size_bytes": order_upload.size_bytes,
        },
    }
    if include_customer:
        payload["customer"] = {
            "public_id": str(order_upload.order.customer.public_id),
            "name": order_upload.order.customer.name,
        }
    return payload


def raise_api_validation_error(error: DjangoValidationError):
    if hasattr(error, "message_dict"):
        raise DRFValidationError(error.message_dict)
    raise DRFValidationError({"detail": error.messages})


def build_download_response(order_upload):
    response = FileResponse(
        order_upload.file.open("rb"),
        as_attachment=True,
        filename=order_upload.original_filename,
        content_type=order_upload.mime_type,
    )
    response["Content-Length"] = str(order_upload.size_bytes)
    return response


class ClientOrderUploadListCreateView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, customer_public_id, order_public_id):
        order, uploads = upload_service.list_customer_order_uploads(
            customer=self.customer,
            order_public_id=order_public_id,
        )
        if order is None:
            raise Http404
        return Response(
            {
                "customer_public_id": str(self.customer.public_id),
                "order_public_id": str(order.public_id),
                "files": [
                    serialize_order_upload(order_upload, include_customer=False)
                    for order_upload in uploads
                ],
            }
        )

    def post(self, request, customer_public_id, order_public_id):
        try:
            order_upload = upload_service.create_upload(
                customer=self.customer,
                actor=request.user,
                uploaded_file=request.FILES.get("file"),
                customer_membership=self.customer_membership,
                order_public_id=order_public_id,
                source="client_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        return Response(serialize_order_upload(order_upload, include_customer=False), status=201)


class ClientOrderUploadDetailView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id, file_public_id):
        order, order_upload = upload_service.get_customer_order_upload(
            customer=self.customer,
            order_public_id=order_public_id,
            upload_public_id=file_public_id,
        )
        if order is None:
            raise Http404
        if order_upload is None:
            raise Http404

        return Response(serialize_order_upload(order_upload, include_customer=False))


class ClientOrderUploadDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id, file_public_id):
        try:
            order_upload = upload_service.download_customer_order_upload(
                customer=self.customer,
                actor=request.user,
                customer_membership=self.customer_membership,
                order_public_id=order_public_id,
                upload_public_id=file_public_id,
                source="client_api",
            )
        except DjangoValidationError as error:
            raise_api_validation_error(error)

        if order_upload is None:
            raise Http404
        return build_download_response(order_upload)


class StaffOrderUploadListView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderUploadReadAccess]

    def get(self, request, order_public_id):
        order = upload_service.get_staff_order(order_public_id=order_public_id)
        if order is None:
            raise Http404

        uploads = upload_service.list_order_uploads(order=order)
        return Response(
            {
                "order_public_id": str(order.public_id),
                "files": [
                    serialize_order_upload(order_upload, include_customer=True)
                    for order_upload in uploads
                ],
            }
        )


class StaffOrderUploadDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderUploadReadAccess]

    def get(self, request, order_public_id, file_public_id):
        order, order_upload = upload_service.get_staff_order_upload(
            order_public_id=order_public_id,
            upload_public_id=file_public_id,
        )
        if order is None:
            raise Http404
        if order_upload is None:
            raise Http404

        return Response(serialize_order_upload(order_upload, include_customer=True))


class StaffOrderUploadDownloadView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderUploadReadAccess]

    def get(self, request, order_public_id, file_public_id):
        order_upload = upload_service.download_staff_order_upload(
            actor=request.user,
            order_public_id=order_public_id,
            upload_public_id=file_public_id,
            source="staff_api",
        )
        if order_upload is None:
            raise Http404
        return build_download_response(order_upload)


class ClientOrderUploadInspectionDetailView(APIView):
    permission_classes = [IsAuthenticated, HasScopedCustomerAccess]

    def get(self, request, customer_public_id, order_public_id, file_public_id):
        order, order_upload, inspection = upload_service.get_customer_upload_inspection(
            customer=self.customer,
            actor=request.user,
            customer_membership=self.customer_membership,
            order_public_id=order_public_id,
            upload_public_id=file_public_id,
            source="client_api",
        )
        if order is None or order_upload is None or inspection is None:
            raise Http404

        return Response(
            serialize_order_upload_inspection(
                inspection,
                order_upload=order_upload,
                include_customer=False,
            )
        )


class StaffOrderUploadInspectionDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderUploadInspectionReadAccess]

    def get(self, request, order_public_id, file_public_id):
        order, order_upload, inspection = upload_service.get_staff_upload_inspection(
            actor=request.user,
            order_public_id=order_public_id,
            upload_public_id=file_public_id,
            source="staff_api",
        )
        if order is None or order_upload is None or inspection is None:
            raise Http404

        return Response(
            serialize_order_upload_inspection(
                inspection,
                order_upload=order_upload,
                include_customer=True,
            )
        )


class StaffOrderUploadDriveSyncDetailView(APIView):
    permission_classes = [IsAuthenticated, HasStaffOrderUploadDriveSyncReadAccess]

    def get(self, request, order_public_id, file_public_id):
        order, order_upload, sync = upload_service.get_staff_upload_drive_sync(
            actor=request.user,
            order_public_id=order_public_id,
            upload_public_id=file_public_id,
            source="staff_api",
        )
        if order is None or order_upload is None or sync is None:
            raise Http404

        return Response(
            serialize_order_upload_drive_sync(
                sync,
                order_upload=order_upload,
            )
        )
