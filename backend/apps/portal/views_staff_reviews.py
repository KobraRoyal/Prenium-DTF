from __future__ import annotations

from collections import Counter

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views import View

from apps.notifications.services.transactional import (
    schedule_file_correction_requested_email,
)
from apps.portal.htmx import with_toast
from apps.portal.views_common import (
    badge_tone_for_status,
    status_label,
    upload_service,
)
from apps.portal.views_staff import StaffOrderContextMixin
from apps.uploads.models import OrderUploadReview
from apps.uploads.services.assets import AssetService
from apps.uploads.services.production_specs import OrderUploadProductionSpecService
from apps.uploads.services.reviews import (
    OrderUploadReviewService,
    OrderUploadReviewTargetNotFound,
)

asset_service = AssetService()
review_service = OrderUploadReviewService()
production_spec_service = OrderUploadProductionSpecService()


def _inspection_context(request, *, order, form_error: str = "", error_upload_id=""):
    uploads = list(upload_service.list_order_uploads(order=order))
    review_counter = Counter()
    automatic_attention_count = 0
    for upload in uploads:
        upload.production_specs = production_spec_service.serialize(order_upload=upload)
        inspection = getattr(upload, "inspection", None)
        if inspection is None or inspection.status in {"warning", "error"}:
            automatic_attention_count += 1
        review = getattr(upload, "atelier_review", None)
        review_counter[
            review.status if review is not None else OrderUploadReview.Status.PENDING
        ] += 1

    return {
        "order": order,
        "uploads": uploads,
        "automatic_attention_count": automatic_attention_count,
        "pending_review_count": review_counter[OrderUploadReview.Status.PENDING],
        "approved_review_count": review_counter[OrderUploadReview.Status.APPROVED],
        "changes_requested_count": review_counter[
            OrderUploadReview.Status.CHANGES_REQUESTED
        ],
        "all_uploads_approved": bool(uploads)
        and review_counter[OrderUploadReview.Status.APPROVED] == len(uploads),
        "review_reasons": OrderUploadReview.Reason.choices,
        "can_review_uploads": request.user.has_perm("uploads.review_orderupload"),
        "form_error": form_error,
        "error_upload_id": str(error_upload_id or ""),
        "badge_tone_for_status": badge_tone_for_status,
        "status_label": status_label,
    }


class StaffOrderPanelInspectionView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/inspection.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderuploadinspection"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        return render(
            request,
            self.template_name,
            _inspection_context(request, order=self.order),
        )


class StaffOrderUploadReviewView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/inspection.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.review_orderupload"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, order_public_id, upload_public_id):
        try:
            review = review_service.review_upload(
                order=self.order,
                upload_public_id=upload_public_id,
                actor=request.user,
                status=request.POST.get("status", ""),
                reason_code=request.POST.get("reason_code", ""),
                comment=request.POST.get("comment", ""),
                source="staff_portal.order_inspection",
            )
        except OrderUploadReviewTargetNotFound as exc:
            raise Http404 from exc
        except ValidationError as exc:
            message = " ".join(getattr(exc, "messages", None) or [str(exc)])
            response = render(
                request,
                self.template_name,
                _inspection_context(
                    request,
                    order=self.order,
                    form_error=message,
                    error_upload_id=upload_public_id,
                ),
            )
            return with_toast(response, message, "error")

        if review.status == OrderUploadReview.Status.CHANGES_REQUESTED:
            schedule_file_correction_requested_email(review_public_id=review.public_id)
            message = "Correction enregistrée. Notification client mise en file d’envoi."
        else:
            message = "Fichier approuvé pour production."
        response = render(
            request,
            self.template_name,
            _inspection_context(request, order=self.order),
        )
        return with_toast(response, message, "success")


class StaffOrderUploadPreviewView(StaffOrderContextMixin, View):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderupload"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id, upload_public_id):
        order_upload = upload_service.get_order_upload(
            order=self.order,
            upload_public_id=upload_public_id,
        )
        if order_upload is None:
            raise Http404
        preview = asset_service.prepare_order_upload_preview(order_upload=order_upload)
        if preview is None:
            raise Http404
        preview_file, content_type = preview
        preview_file.open("rb")
        response = FileResponse(preview_file, content_type=content_type)
        response["Content-Disposition"] = "inline"
        response["Cache-Control"] = "private, max-age=300"
        return response
