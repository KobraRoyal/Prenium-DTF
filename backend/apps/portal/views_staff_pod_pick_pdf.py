from __future__ import annotations

from io import BytesIO

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.urls import reverse
from django.views import View

from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin

pick_session_service = PodPickSessionService()


class StaffPodPickSessionPdfView(StaffPodPermissionMixin, View):
    def get(self, request, session_public_id, document_kind):
        kind = "labels" if document_kind == "etiquettes" else "picking"
        if document_kind not in {"picking", "etiquettes"}:
            raise Http404
        try:
            session, payload = pick_session_service.pdf_bytes(
                actor=request.user,
                session_public_id=session_public_id,
                kind=kind,
            )
        except ValidationError as exc:
            messages.error(request, validation_message(exc))
            return HttpResponseRedirect(reverse("portal:staff-pod-hub"))
        suffix = "zebra" if kind == "labels" else "picking"
        response = FileResponse(BytesIO(payload), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{session.code}-{suffix}.pdf"'
        return response
