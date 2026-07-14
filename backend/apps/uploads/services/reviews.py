from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.uploads.models import OrderUpload, OrderUploadReview


class OrderUploadReviewTargetNotFound(Exception):
    pass


class OrderUploadReviewService:
    permission_name = "uploads.review_orderupload"
    max_comment_length = 2000

    @transaction.atomic
    def review_upload(
        self,
        *,
        order,
        upload_public_id,
        actor,
        status: str,
        reason_code: str = "",
        comment: str = "",
        source: str,
    ) -> OrderUploadReview:
        if not getattr(actor, "is_authenticated", False) or not actor.has_perm(
            self.permission_name
        ):
            raise PermissionDenied

        order_upload = (
            OrderUpload.objects.select_for_update()
            .for_order(order)
            .filter(public_id=upload_public_id)
            .first()
        )
        if order_upload is None:
            raise OrderUploadReviewTargetNotFound

        normalized_status = str(status or "").strip()
        allowed_statuses = {
            OrderUploadReview.Status.APPROVED,
            OrderUploadReview.Status.CHANGES_REQUESTED,
        }
        if normalized_status not in allowed_statuses:
            raise ValidationError("Décision Atelier invalide.")

        normalized_reason = str(reason_code or "").strip()
        normalized_comment = str(comment or "").strip()
        if len(normalized_comment) > self.max_comment_length:
            raise ValidationError(
                f"Le commentaire est limité à {self.max_comment_length} caractères."
            )

        if normalized_status == OrderUploadReview.Status.CHANGES_REQUESTED:
            valid_reasons = {value for value, _label in OrderUploadReview.Reason.choices}
            if normalized_reason not in valid_reasons:
                raise ValidationError("Sélectionnez le motif de la correction demandée.")
            if normalized_reason == OrderUploadReview.Reason.OTHER and not normalized_comment:
                raise ValidationError("Précisez la correction attendue pour le motif « Autre ».")
        else:
            normalized_reason = ""
            normalized_comment = ""

        review, _created = OrderUploadReview.objects.select_for_update().get_or_create(
            order_upload=order_upload
        )
        previous_status = review.status
        review.status = normalized_status
        review.reason_code = normalized_reason
        review.comment = normalized_comment
        review.reviewed_by = actor
        review.reviewed_at = timezone.now()
        if normalized_status == OrderUploadReview.Status.CHANGES_REQUESTED:
            review.client_notified_at = None
        review.full_clean()
        review.save()

        record_event(
            action="order_upload.reviewed",
            actor=actor,
            target=review,
            metadata={
                "order_public_id": str(order.public_id),
                "customer_public_id": str(order.customer.public_id),
                "order_upload_public_id": str(order_upload.public_id),
                "previous_status": previous_status,
                "review_status": review.status,
                "reason_code": review.reason_code,
                "source": source,
            },
        )
        return review

    @transaction.atomic
    def mark_client_notified(self, *, review_public_id) -> OrderUploadReview | None:
        review = (
            OrderUploadReview.objects.select_for_update()
            .select_related("order_upload", "order_upload__order", "order_upload__order__customer")
            .filter(public_id=review_public_id)
            .first()
        )
        if review is None:
            return None
        review.client_notified_at = timezone.now()
        review.save(update_fields=["client_notified_at", "updated_at"])
        record_event(
            action="order_upload.review_notification_sent",
            target=review,
            metadata={
                "order_public_id": str(review.order_upload.order.public_id),
                "customer_public_id": str(review.order_upload.order.customer.public_id),
                "order_upload_public_id": str(review.order_upload.public_id),
                "review_status": review.status,
            },
        )
        return review
