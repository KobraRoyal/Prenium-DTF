from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.views import View

from apps.portal.views_common import (
    badge_tone_for_status,
    staff_order_upload_rows,
    status_label,
    upload_service,
)
from apps.portal.views_staff import StaffOrderContextMixin
from apps.uploads.models import OrderUploadDriveSync


class StaffOrderPanelUploadsView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/uploads.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderupload"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _staff_uploads_context(self, request):
        return {
            "order": self.order,
            "upload_rows": staff_order_upload_rows(self.order),
            "badge_tone_for_status": badge_tone_for_status,
            "status_label": status_label,
        }

    def get(self, request, order_public_id):
        return render(
            request,
            self.template_name,
            self._staff_uploads_context(request),
        )


def _upload_needs_drive_attention(upload) -> bool:
    """True si pas de synchro, synchro non OK, ou erreur résiduelle."""
    sync = getattr(upload, "drive_sync", None)
    if sync is None:
        return True
    if sync.status != OrderUploadDriveSync.Status.SYNCED:
        return True
    if (sync.last_error or "").strip():
        return True
    return False


class StaffOrderPanelDriveSyncView(StaffOrderContextMixin, View):
    template_name = "portal/staff/panels/drive_sync.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perm("uploads.view_orderuploaddrivesync"):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, order_public_id):
        uploads = list(upload_service.list_order_uploads(order=self.order))
        drive_sync_problems = [u for u in uploads if _upload_needs_drive_attention(u)]
        return render(
            request,
            self.template_name,
            {
                "order": self.order,
                "uploads": uploads,
                "drive_sync_problems": drive_sync_problems,
                "badge_tone_for_status": badge_tone_for_status,
                "status_label": status_label,
            },
        )
