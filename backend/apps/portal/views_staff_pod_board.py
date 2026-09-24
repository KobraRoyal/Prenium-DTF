from __future__ import annotations

from io import BytesIO

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.inventory.services import WarehouseLayoutService
from apps.pod.services import PodRipLotService, PrintTechniqueService
from apps.pod.services.ops_demo import PodOpsBootstrapService
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav

print_technique_service = PrintTechniqueService()
warehouse_layout_service = WarehouseLayoutService()
ops_bootstrap_service = PodOpsBootstrapService()
rip_lot_service = PodRipLotService()
pick_session_service = PodPickSessionService()


class StaffPodHubView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/hub.html"

    def get(self, request):
        self._ensure_seed(request)
        return render(request, self.template_name, self._context(request))

    def post(self, request):
        self._ensure_seed(request)
        intent = request.POST.get("intent", "")
        selected_ids = request.POST.getlist("work_item_public_ids")
        try:
            if intent == "set_quantity":
                rip_lot_service.set_queued_quantity(
                    actor=request.user,
                    source="staff_pod_board",
                    work_item_public_id=request.POST.get("work_item_public_id"),
                    quantity=request.POST.get("quantity"),
                )
                messages.success(request, "Quantité enregistrée.")
                return HttpResponseRedirect(reverse("portal:staff-pod-hub"))
            if intent == "print_session":
                session = pick_session_service.open_session(
                    actor=request.user,
                    source="staff_pod_board",
                    work_item_public_ids=selected_ids,
                )
                messages.success(
                    request,
                    f"Session {session.code} prête — {session.piece_count} pièce(s). "
                    "Imprimez le picking A4 et les étiquettes Zebra.",
                )
                return HttpResponseRedirect(reverse("portal:staff-pod-hub"))
            if intent == "prepare":
                lot = rip_lot_service.prepare_dtf_lot(
                    actor=request.user,
                    source="staff_pod_board",
                    work_item_public_ids=selected_ids,
                )
                messages.success(
                    request,
                    f"Lot {lot.code} préparé — {lot.file_count} fichier(s) RIP. "
                    "Seule la sélection a été incluse.",
                )
                return HttpResponseRedirect(
                    reverse(
                        "portal:staff-pod-rip-lot-detail",
                        kwargs={"lot_public_id": lot.public_id},
                    )
                )
            raise ValidationError("Action inconnue.")
        except PermissionDenied:
            raise
        except ValidationError as exc:
            return render(
                request,
                self.template_name,
                {**self._context(request), "form_error": validation_message(exc)},
                status=400,
            )

    def _ensure_seed(self, request):
        print_technique_service.ensure_dtf_technique(actor=request.user)
        warehouse_layout_service.ensure_default_layout(actor=request.user)
        if request.user.has_perm("pod.manage_pod_catalog") and request.user.has_perm(
            "inventory.manage_warehouse"
        ):
            ops_bootstrap_service.ensure_ready(actor=request.user)

    def _context(self, request):
        readiness = (
            request.GET.get("queue") or request.GET.get("readiness") or "all"
        ).strip().lower()
        q = (request.GET.get("q") or "").strip()
        try:
            page = int(request.GET.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        try:
            press_page = int(request.GET.get("press_page") or 1)
        except (TypeError, ValueError):
            press_page = 1
        board = rip_lot_service.production_board(
            actor=request.user,
            readiness=readiness,
            q=q,
            page=page,
            press_page=press_page,
        )
        sessions = list(pick_session_service.list_recent(actor=request.user))
        for session in sessions:
            active = sum(1 for line in session.lines.all() if line.voided_at is None)
            session.active_piece_count = active
            session.is_voided = active == 0 and session.piece_count > 0
        return {
            **_nav(),
            "board": board,
            "pick_sessions": sessions,
            "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            "form_error": "",
            "search_query": q,
            "active_queue": readiness if readiness in {"ready", "blocked"} else "",
            "page_obj": board.get("page_obj"),
            "press_page_obj": board.get("press_page_obj"),
        }


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
