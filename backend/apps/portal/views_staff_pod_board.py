from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.pod.models import PodPickSessionLine
from apps.pod.services import PodRipLotService
from apps.pod.services.operate_workflow import PodOperateWorkflowService
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav

rip_lot_service = PodRipLotService()
pick_session_service = PodPickSessionService()
operate_workflow = PodOperateWorkflowService()


class StaffPodHubView(StaffPodPermissionMixin, View):
    template_name = "portal/staff/pod/hub.html"

    def get(self, request):
        return render(request, self.template_name, self._context(request))

    def post(self, request):
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
                    "Imprimez le picking A4 et les étiquettes Zebra. "
                    "Les visuels HD partent vers Drive pour impression.",
                )
                return HttpResponseRedirect(self._pick_redirect(session.public_id))
            if intent == "confirm_pick":
                line = pick_session_service.confirm_pick(
                    actor=request.user,
                    source="staff_pod_board",
                    scan_identifier=request.POST.get("scan_identifier", ""),
                    scanned_bin_code=request.POST.get("scanned_bin_code", ""),
                )
                messages.success(
                    request,
                    f"Pièce {line.scan_identifier} prélevée. Stock débité.",
                )
                return HttpResponseRedirect(self._pick_redirect(line.session.public_id))
            if intent == "reissue_legacy_session":
                count = pick_session_service.reissue_legacy_session(
                    actor=request.user,
                    source="staff_pod_board",
                    session_public_id=request.POST.get("session_public_id"),
                )
                messages.success(request, f"{count} ancienne(s) étiquette(s) annulée(s).")
                session_id = request.POST.get("session_public_id") or ""
                return HttpResponseRedirect(self._pick_redirect(session_id))
            if intent == "confirm_dtf_print":
                session = pick_session_service.get_session(
                    actor=request.user,
                    session_public_id=request.POST.get("session_public_id"),
                )
                operate_workflow.confirm_dtf_print(
                    actor=request.user,
                    session=session,
                    source="staff_pod_board",
                )
                messages.success(request, "Impression DTF validée — vous pouvez passer à la pose.")
                return HttpResponseRedirect(self._pick_redirect(session.public_id))
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
            pick_scan_identifier = ""
            pick_bin_code = ""
            if intent == "confirm_pick":
                pick_scan_identifier = request.POST.get("scan_identifier", "")
                pick_bin_code = request.POST.get("scanned_bin_code", "")
            return render(
                request,
                self.template_name,
                {
                    **self._context(
                        request,
                        pick_scan_identifier=pick_scan_identifier,
                        pick_bin_code=pick_bin_code,
                        preferred_session_id=request.POST.get("session_public_id", ""),
                    ),
                    "form_error": validation_message(exc),
                    "pick_form_error": (
                        validation_message(exc) if intent == "confirm_pick" else ""
                    ),
                },
                status=200 if request.headers.get("HX-Request") == "true" else 400,
            )

    def _pick_redirect(self, session_public_id) -> str:
        hub = reverse("portal:staff-pod-hub")
        if session_public_id:
            return f"{hub}?session={session_public_id}#pod-pick-workflow"
        return f"{hub}#pod-pick-workflow"

    def _context(
        self,
        request,
        *,
        pick_scan_identifier: str = "",
        pick_bin_code: str = "",
        preferred_session_id: str = "",
    ):
        readiness = (
            (request.GET.get("queue") or request.GET.get("readiness") or "all").strip().lower()
        )
        q = (request.GET.get("q") or "").strip()
        try:
            page = int(request.GET.get("page") or 1)
        except (TypeError, ValueError):
            page = 1
        board = rip_lot_service.production_board(
            actor=request.user,
            readiness=readiness,
            q=q,
            page=page,
        )
        sessions = pick_session_service.list_recent(actor=request.user)
        session_key = (preferred_session_id or request.GET.get("session") or "").strip()
        active = self._resolve_active_session(sessions, session_key)
        pick_ctx = self._session_pick_context(active)
        pick_rip_ready_items = rip_lot_service.rip_ready_work_items_for_session(session=active)
        operate_rail = operate_workflow.session_rail(session=active)
        return {
            **_nav(),
            "board": board,
            "pick_sessions": sessions,
            "pick_rip_ready_items": pick_rip_ready_items,
            "operate_rail": operate_rail,
            "pick_reserved_count": sum(session.reserved_piece_count for session in sessions),
            "pick_untracked_count": sum(session.untracked_piece_count for session in sessions),
            "can_manage_catalog": request.user.has_perm("pod.manage_pod_catalog"),
            "can_operate_production": request.user.has_perm("pod.operate_pod_production"),
            "form_error": "",
            "search_query": q,
            "active_queue": readiness if readiness in {"ready", "blocked"} else "",
            "page_obj": board.get("page_obj"),
            "pick_scan_identifier": pick_scan_identifier,
            "pick_bin_code": pick_bin_code,
            "pick_form_error": "",
            **pick_ctx,
        }

    def _resolve_active_session(self, sessions, session_key: str):
        if not sessions:
            return None
        if session_key:
            for session in sessions:
                if str(session.public_id) == session_key or session.code == session_key:
                    return session
        for session in sessions:
            if not session.is_voided and session.reserved_piece_count > 0:
                return session
        for session in sessions:
            if not session.is_voided:
                return session
        return sessions[0]

    def _session_pick_context(self, session) -> dict:
        if session is None:
            return {
                "active_pick_session": None,
                "pick_remaining_lines": [],
                "pick_done_lines": [],
                "pick_untracked_lines": [],
                "pick_next_line": None,
                "pick_total_active": 0,
            }
        lines = list(getattr(session, "active_lines_for_display", []) or [])
        remaining = [
            line
            for line in lines
            if line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED
        ]
        done = [
            line
            for line in lines
            if line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED
        ]
        untracked = [
            line
            for line in lines
            if line.reservation_status == PodPickSessionLine.ReservationStatus.UNTRACKED
        ]
        return {
            "active_pick_session": session,
            "pick_remaining_lines": remaining,
            "pick_done_lines": done,
            "pick_untracked_lines": untracked,
            "pick_next_line": remaining[0] if remaining else None,
            "pick_total_active": len(lines),
        }
