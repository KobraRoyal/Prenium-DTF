from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views import View

from apps.pod.services.operate_workflow import PodOperateWorkflowService
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.validation import validation_message
from apps.portal.views_staff_pod import StaffPodPermissionMixin, _nav

operate_workflow = PodOperateWorkflowService()
pick_session_service = PodPickSessionService()
rip_lot_service = PodRipLotService()


class StaffPodSuiviView(StaffPodPermissionMixin, View):
    """Tableau de suivi Operate — avancement sessions sans dupliquer les postes."""

    template_name = "portal/staff/pod/suivi.html"

    def get(self, request):
        stage = (request.GET.get("stage") or "all").strip().lower()
        board = operate_workflow.board(actor=request.user, stage=stage)
        return render(
            request,
            self.template_name,
            {
                **_nav(),
                "board": board,
                "form_error": "",
                "can_operate_production": request.user.has_perm("pod.operate_pod_production"),
            },
        )

    def post(self, request):
        intent = request.POST.get("intent", "")
        stage = (request.POST.get("stage") or request.GET.get("stage") or "all").strip().lower()
        try:
            if intent == "confirm_dtf_print":
                session = pick_session_service.get_session(
                    actor=request.user,
                    session_public_id=request.POST.get("session_public_id"),
                )
                operate_workflow.confirm_dtf_print(
                    actor=request.user,
                    session=session,
                    source="staff_pod_suivi",
                )
                messages.success(request, "Impression DTF validée.")
            elif intent == "sync_drive":
                lot_public_id = request.POST.get("lot_public_id")
                if not lot_public_id:
                    raise ValidationError("Lot RIP manquant pour la synchronisation Drive.")
                from django.conf import settings

                if not getattr(settings, "GOOGLE_DRIVE_SYNC_ENABLED", False):
                    messages.info(request, "Sync Drive désactivée (GOOGLE_DRIVE_SYNC_ENABLED).")
                else:
                    rip_lot_service.request_drive_sync(
                        actor=request.user,
                        lot_public_id=lot_public_id,
                    )
                    messages.success(request, "Synchronisation Drive en file d’attente.")
            else:
                raise ValidationError("Action inconnue.")
        except PermissionDenied:
            raise
        except ValidationError as exc:
            board = operate_workflow.board(actor=request.user, stage=stage)
            return render(
                request,
                self.template_name,
                {
                    **_nav(),
                    "board": board,
                    "form_error": validation_message(exc),
                    "can_operate_production": request.user.has_perm("pod.operate_pod_production"),
                },
                status=400,
            )
        redirect = reverse("portal:staff-pod-suivi")
        if stage and stage != "all":
            redirect = f"{redirect}?stage={stage}"
        return HttpResponseRedirect(redirect)
