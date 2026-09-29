from __future__ import annotations

from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.urls import reverse
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import (
    PodPickSession,
    PodPickSessionLine,
    PodRipLot,
    PodUnit,
)
from apps.pod.services.validation import require_staff_perm


@dataclass(frozen=True)
class OperateStep:
    key: str
    label: str
    state: str  # todo | active | done | locked
    detail: str
    href: str
    action_label: str


@dataclass(frozen=True)
class SessionBoardRow:
    session: PodPickSession
    stage: str
    stage_label: str
    pick_done: int
    pick_total: int
    print_state: str
    pose_done: int
    pose_total: int
    qc_done: int
    qc_total: int
    orders: tuple[str, ...]
    cta_url: str
    cta_label: str
    detail: str
    lot_public_id: str
    rip_path: str
    drive_synced: bool
    drive_error: str


class PodOperateWorkflowService:
    manage_permission = "pod.operate_pod_production"
    view_permission = "pod.access_pod_atelier"

    STAGE_LABELS = {
        "pick": "Prélèvement",
        "print": "Impression DTF",
        "pose": "Pose",
        "qc": "Contrôle qualité",
        "done": "Terminé",
    }

    def session_rail(self, *, session: PodPickSession | None) -> list[OperateStep] | None:
        if session is None:
            return None
        snapshot = self._session_snapshot(session)
        return [
            OperateStep(
                key="pick",
                label="Prélèvement",
                state=snapshot["pick_state"],
                detail=snapshot["pick_detail"],
                href="#pod-pick-scan",
                action_label="Scanner",
            ),
            OperateStep(
                key="print",
                label="Impression DTF",
                state=snapshot["print_state"],
                detail=snapshot["print_detail"],
                href="#pod-operate-print",
                action_label="Valider impression",
            ),
            OperateStep(
                key="pose",
                label="Pose",
                state=snapshot["pose_state"],
                detail=snapshot["pose_detail"],
                href="pose",
                action_label="Ouvrir Pose",
            ),
        ]

    def board(self, *, actor, stage: str = "all", limit: int = 40) -> dict:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.operate.board",
            action="pod.operate.permission_rejected",
        )
        stage_key = (stage or "all").strip().lower()
        if stage_key not in {"all", "pick", "print", "pose", "qc", "done"}:
            stage_key = "all"
        sessions = list(
            PodPickSession.objects.prefetch_related(
                Prefetch(
                    "lines",
                    queryset=PodPickSessionLine.objects.filter(voided_at__isnull=True)
                    .select_related("work_item")
                    .only(
                        "id",
                        "session_id",
                        "work_item_id",
                        "unit_id",
                        "sequence",
                        "reservation_status",
                        "shopify_order_number",
                        "voided_at",
                    )
                    .order_by("sequence"),
                )
            )
            .only("id", "public_id", "code", "piece_count", "created_at")
            .order_by("-created_at")[: max(int(limit) * 2, 20)]
        )
        lots_by_code: dict[str, PodRipLot] = {}
        session_codes = [session.code for session in sessions]
        if session_codes:
            for lot in (
                PodRipLot.objects.filter(
                    nas_relative_path__in=session_codes,
                    status=PodRipLot.Status.PREPARED,
                )
                .select_related("technique")
                .only(
                    "id",
                    "public_id",
                    "nas_relative_path",
                    "file_count",
                    "drive_synced_at",
                    "drive_error",
                    "operator_print_confirmed_at",
                    "prepared_at",
                    "technique_id",
                    "technique__code",
                    "technique__rip_directory",
                )
                .order_by("-prepared_at")
            ):
                lots_by_code.setdefault(lot.nas_relative_path, lot)
        unit_ids = [
            line.unit_id
            for session in sessions
            for line in session.lines.all()
            if line.unit_id
        ]
        units_by_id = {
            unit.pk: unit
            for unit in PodUnit.objects.filter(pk__in=unit_ids).only(
                "pk", "status", "scan_identifier"
            )
        }
        rows: list[SessionBoardRow] = []
        counts = {"pick": 0, "print": 0, "pose": 0, "qc": 0, "done": 0}
        for session in sessions:
            lines = [
                line
                for line in session.lines.all()
                if line.reservation_status != PodPickSessionLine.ReservationStatus.UNTRACKED
            ]
            if not lines:
                continue
            lot = lots_by_code.get(session.code)
            units = [units_by_id[line.unit_id] for line in lines if line.unit_id in units_by_id]
            row = self._row_from_session(session=session, lines=lines, lot=lot, units=units)
            counts[row.stage] = counts.get(row.stage, 0) + 1
            if stage_key == "all":
                if row.stage != "done":
                    rows.append(row)
            elif row.stage == stage_key:
                rows.append(row)
        rows = rows[: max(int(limit), 1)]
        waiting_press = PodUnit.objects.filter(status=PodUnit.Status.WAITING_PRESS).count()
        waiting_qc = PodUnit.objects.filter(status=PodUnit.Status.PRESSED).count()
        return {
            "stage": stage_key,
            "counts": counts,
            "active_count": sum(counts[k] for k in ("pick", "print", "pose", "qc")),
            "waiting_press": waiting_press,
            "waiting_qc": waiting_qc,
            "rows": rows,
        }

    def _row_from_session(
        self,
        *,
        session: PodPickSession,
        lines: list[PodPickSessionLine],
        lot: PodRipLot | None,
        units: list[PodUnit],
    ) -> SessionBoardRow:
        pick_total = len(lines)
        pick_done = sum(
            1
            for line in lines
            if line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED
        )
        is_dtf = lot is not None and (lot.technique.code or "").lower() == "dtf"
        print_confirmed = bool(lot and (not is_dtf or lot.operator_print_confirmed_at))
        pose_total = len(units)
        pose_done = sum(1 for unit in units if unit.status != PodUnit.Status.WAITING_PRESS)
        waiting_pose = sum(1 for unit in units if unit.status == PodUnit.Status.WAITING_PRESS)
        waiting_qc = sum(1 for unit in units if unit.status == PodUnit.Status.PRESSED)
        qc_done = sum(1 for unit in units if unit.status == PodUnit.Status.QC_PASSED)
        qc_total = sum(
            1
            for unit in units
            if unit.status
            in {
                PodUnit.Status.PRESSED,
                PodUnit.Status.QC_PASSED,
                PodUnit.Status.QC_FAILED,
            }
        )

        if pick_done < pick_total:
            stage = "pick"
            detail = f"{pick_done}/{pick_total} prélevée(s)"
            cta_url = (
                f"{reverse('portal:staff-pod-hub')}?session={session.public_id}#pod-pick-workflow"
            )
            cta_label = "Continuer le prélèvement"
        elif lot is None or (is_dtf and not lot.operator_print_confirmed_at):
            stage = "print"
            if lot is None:
                detail = "Lot DTF à préparer / sync Drive"
            elif lot.drive_error:
                detail = f"Drive : {lot.drive_error[:80]}"
            else:
                detail = f"{lot.file_count} fichier(s) — valider l’impression"
            cta_url = (
                f"{reverse('portal:staff-pod-hub')}?session={session.public_id}#pod-operate-print"
            )
            cta_label = "Valider impression"
        elif waiting_pose > 0 or (pose_total and pose_done < pose_total):
            stage = "pose"
            detail = f"{pose_done}/{pose_total or pick_total} posée(s)"
            cta_url = reverse("portal:staff-pod-pose-dtf")
            cta_label = "Ouvrir Pose"
        elif waiting_qc > 0:
            stage = "qc"
            detail = f"{qc_done}/{max(qc_total, waiting_qc)} contrôlée(s)"
            cta_url = reverse("portal:staff-pod-qc")
            cta_label = "Ouvrir QC"
        else:
            stage = "done"
            detail = "Session terminée"
            cta_url = reverse("portal:staff-pod-hub")
            cta_label = "À produire"

        orders = tuple(
            dict.fromkeys(line.shopify_order_number for line in lines if line.shopify_order_number)
        )
        print_state = "done" if print_confirmed else ("active" if lot is not None else "todo")
        return SessionBoardRow(
            session=session,
            stage=stage,
            stage_label=self.STAGE_LABELS[stage],
            pick_done=pick_done,
            pick_total=pick_total,
            print_state=print_state,
            pose_done=pose_done,
            pose_total=pose_total or pick_total,
            qc_done=qc_done,
            qc_total=max(qc_total, waiting_qc, pose_total or 0),
            orders=orders,
            cta_url=cta_url,
            cta_label=cta_label,
            detail=detail,
            lot_public_id=str(lot.public_id) if lot is not None else "",
            rip_path=(
                f"POD_RIP/{lot.nas_relative_path}/{lot.technique.rip_directory}/"
                if lot is not None
                else ""
            ),
            drive_synced=bool(lot and lot.drive_synced_at),
            drive_error=(lot.drive_error if lot is not None else "") or "",
        )

    def _session_snapshot(self, session: PodPickSession) -> dict:
        lines = [
            line
            for line in session.lines.all()
            if line.voided_at is None
            and line.reservation_status != PodPickSessionLine.ReservationStatus.UNTRACKED
        ]
        pick_total = len(lines)
        pick_done = sum(
            1
            for line in lines
            if line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED
        )
        lot = (
            PodRipLot.objects.filter(
                nas_relative_path=session.code,
                status=PodRipLot.Status.PREPARED,
            )
            .select_related("technique")
            .order_by("-prepared_at")
            .first()
        )
        is_dtf = lot is not None and (lot.technique.code or "").lower() == "dtf"
        units = list(
            PodUnit.objects.filter(pick_line__session=session, pick_line__voided_at__isnull=True)
        )
        pose_total = len(units)
        pose_done = sum(1 for unit in units if unit.status != PodUnit.Status.WAITING_PRESS)

        if pick_total == 0:
            pick_state, pick_detail = "todo", "Générez picking + Zebra."
        elif pick_done >= pick_total:
            pick_state, pick_detail = "done", f"{pick_done}/{pick_total} pièce(s) prélevée(s)."
        else:
            pick_state, pick_detail = "active", f"{pick_done}/{pick_total} — scannez pièce + bin."

        if lot is None:
            print_state, print_detail = (
                "todo",
                "Lot DTF en attente (auto à la session ou bouton ci-dessous).",
            )
        elif is_dtf and not lot.operator_print_confirmed_at:
            print_state = "active"
            if lot.drive_synced_at:
                print_detail = (
                    f"{lot.file_count} fichier(s) sur Drive — confirmez l’impression lancée."
                )
            elif lot.drive_error:
                print_detail = f"Drive : {lot.drive_error[:120]}"
            else:
                print_detail = f"{lot.file_count} fichier(s) prêts — sync Drive en cours."
        else:
            print_state = "done"
            print_detail = (
                "Impression DTF validée." if is_dtf else f"Lot {lot.technique.code.upper()} prêt."
            )

        pose_unlocked = lot is not None and (not is_dtf or lot.operator_print_confirmed_at)
        if pose_total == 0:
            pose_state = "locked" if not pose_unlocked else "todo"
            pose_detail = (
                "Créez le lot DTF pour activer la pose." if not lot else "Pièces en préparation."
            )
        elif pose_done >= pose_total:
            pose_state, pose_detail = "done", f"{pose_done}/{pose_total} posée(s) — passez au QC."
        elif not pose_unlocked:
            pose_state, pose_detail = "locked", "Validez l’impression DTF avant la pose."
        else:
            pose_state, pose_detail = "active", f"{pose_done}/{pose_total} — poste Pose."

        return {
            "pick_state": pick_state,
            "pick_detail": pick_detail,
            "print_state": print_state,
            "print_detail": print_detail,
            "pose_state": pose_state,
            "pose_detail": pose_detail,
        }

    def confirm_dtf_print(
        self,
        *,
        actor,
        session: PodPickSession,
        source: str,
    ) -> PodRipLot:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.operate.print_confirm_rejected",
        )
        lot = (
            PodRipLot.objects.select_related("technique")
            .filter(nas_relative_path=session.code, status=PodRipLot.Status.PREPARED)
            .order_by("-prepared_at")
            .first()
        )
        if lot is None:
            raise ValidationError(
                "Aucun lot DTF pour cette session. Attendez la préparation auto ou lancez « Préparer lot DTF »."
            )
        if (lot.technique.code or "").lower() != "dtf":
            raise ValidationError("Cette session n’a pas de lot DTF à valider.")
        if lot.operator_print_confirmed_at:
            return lot
        lot.operator_print_confirmed_at = timezone.now()
        lot.operator_print_confirmed_by = actor
        lot.save(
            update_fields=[
                "operator_print_confirmed_at",
                "operator_print_confirmed_by",
                "updated_at",
            ]
        )
        record_event(
            action="pod.operate.dtf_print_confirmed",
            actor=actor,
            target=lot,
            metadata={"session_code": session.code, "source": source},
        )
        return lot

    def require_pose_unlocked(self, *, unit: PodUnit) -> None:
        lot = unit.lot
        if lot is None:
            return
        if (lot.technique.code or "").lower() != "dtf":
            return
        if lot.operator_print_confirmed_at:
            return
        raise ValidationError(
            "Impression DTF non validée pour cette session. "
            "Sur À produire, confirmez « Impression lancée » avant la pose."
        )
