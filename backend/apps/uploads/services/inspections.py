from __future__ import annotations

from django.utils import timezone

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event
from apps.uploads.models import OrderUpload, OrderUploadInspection
from apps.uploads.services.metadata import UploadMetadataExtractionService


class OrderUploadInspectionService:
    def __init__(self, metadata_service: UploadMetadataExtractionService | None = None):
        self.metadata_service = metadata_service or UploadMetadataExtractionService()

    def inspect_upload(
        self,
        *,
        order_upload: OrderUpload,
        actor,
        source: str,
    ) -> OrderUploadInspection:
        try:
            extracted = self.metadata_service.extract(order_upload)
            inspection = OrderUploadInspection.objects.update_or_create(
                order_upload=order_upload,
                defaults={
                    "status": extracted.status,
                    "summary_message": extracted.summary_message,
                    "file_kind": extracted.file_kind,
                    "file_extension": extracted.file_extension,
                    "image_width": extracted.image_width,
                    "image_height": extracted.image_height,
                    "metadata": extracted.metadata,
                    "checked_at": timezone.now(),
                },
            )[0]
            audit_status = (
                AuditLogEntry.Status.FAILURE
                if inspection.status == OrderUploadInspection.Status.ERROR
                else AuditLogEntry.Status.SUCCESS
            )
            audit_message = inspection.summary_message
        except ValueError:
            inspection = OrderUploadInspection.objects.update_or_create(
                order_upload=order_upload,
                defaults={
                    "status": OrderUploadInspection.Status.ERROR,
                    "summary_message": "Image metadata could not be read.",
                    "file_kind": "",
                    "file_extension": "",
                    "image_width": None,
                    "image_height": None,
                    "metadata": {
                        "mime_type": order_upload.mime_type,
                        "size_bytes": order_upload.size_bytes,
                    },
                    "checked_at": timezone.now(),
                },
            )[0]
            audit_status = AuditLogEntry.Status.FAILURE
            audit_message = inspection.summary_message
        except OSError:
            inspection = OrderUploadInspection.objects.update_or_create(
                order_upload=order_upload,
                defaults={
                    "status": OrderUploadInspection.Status.ERROR,
                    "summary_message": "File is unavailable for inspection.",
                    "file_kind": "",
                    "file_extension": "",
                    "image_width": None,
                    "image_height": None,
                    "metadata": {
                        "mime_type": order_upload.mime_type,
                        "size_bytes": order_upload.size_bytes,
                    },
                    "checked_at": timezone.now(),
                },
            )[0]
            audit_status = AuditLogEntry.Status.FAILURE
            audit_message = inspection.summary_message

        record_event(
            action="order_upload.inspected",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            status=audit_status,
            message=audit_message,
            metadata={
                "order_public_id": str(order_upload.order.public_id),
                "customer_public_id": str(order_upload.order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "inspection_public_id": str(inspection.public_id),
                "inspection_status": inspection.status,
                "file_kind": inspection.file_kind,
                "source": source,
            },
        )
        return inspection

    def ensure_inspection(
        self,
        *,
        order_upload: OrderUpload,
        actor,
        source: str,
    ) -> OrderUploadInspection:
        inspection = getattr(order_upload, "inspection", None)
        if inspection is not None:
            return inspection
        return self.inspect_upload(order_upload=order_upload, actor=actor, source=source)

    def record_view_event(
        self,
        *,
        order_upload: OrderUpload,
        inspection: OrderUploadInspection,
        actor,
        source: str,
        audience: str,
        customer_membership_public_id: str | None = None,
    ) -> None:
        metadata = {
            "order_public_id": str(order_upload.order.public_id),
            "customer_public_id": str(order_upload.order.customer.public_id),
            "order_upload_public_id": str(order_upload.public_id),
            "inspection_public_id": str(inspection.public_id),
            "inspection_status": inspection.status,
            "file_kind": inspection.file_kind,
            "audience": audience,
            "source": source,
        }
        if customer_membership_public_id is not None:
            metadata["customer_membership_public_id"] = customer_membership_public_id

        record_event(
            action="order_upload.inspection_viewed",
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            target=order_upload,
            metadata=metadata,
        )
