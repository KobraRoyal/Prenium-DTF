from __future__ import annotations

import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import PodPickSession, PodPickSessionLine, PodRipWorkItem
from apps.pod.services.documents import new_scan_identifier
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.validation import require_staff_perm


class PodPickSessionService:
    manage_permission = "pod.manage_pod_catalog"
    view_permission = "pod.access_pod_atelier"

    def list_recent(self, *, actor, limit: int = 8):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.pick",
            action="pod.pick.permission_rejected",
        )
        return PodPickSession.objects.prefetch_related("lines").all()[:limit]

    def get_session(self, *, actor, session_public_id) -> PodPickSession:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.pick",
            action="pod.pick.permission_rejected",
        )
        session = (
            PodPickSession.objects.filter(public_id=session_public_id)
            .prefetch_related("lines")
            .first()
        )
        if session is None:
            raise ValidationError("Session de picking introuvable.")
        return session

    def void_lines_for_work_item(self, *, work_item: PodRipWorkItem, reason: str = "") -> int:
        now = timezone.now()
        updated = (
            PodPickSessionLine.objects.filter(work_item=work_item, voided_at__isnull=True).update(
                voided_at=now,
                updated_at=now,
            )
        )
        if updated:
            record_event(
                action="pod.pick.lines_voided",
                target=work_item,
                metadata={"count": updated, "reason": reason[:120]},
            )
        return updated

    def open_session(
        self,
        *,
        actor,
        source: str,
        work_item_public_ids: list[str],
    ) -> PodPickSession:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.pick.permission_rejected",
        )
        selected = {str(value) for value in work_item_public_ids if value}
        if not selected:
            raise ValidationError("Sélectionnez au moins une commande.")
        board = PodRipLotService().production_board(actor=actor)
        drafts = []
        for group in board["picking_groups"]:
            for line in group["lines"]:
                if not line["editable"] or int(line["quantity"] or 0) < 1:
                    continue
                if line["work_item_public_id"] not in selected:
                    continue
                drafts.append((group, line))
        if not drafts:
            raise ValidationError(
                "Aucune pièce nouvelle dans la sélection. "
                "Les commandes déjà étiquetées restent dans leur session."
            )
        code = f"PICK-{timezone.now():%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
        with transaction.atomic():
            session = PodPickSession.objects.create(code=code, created_by=actor, piece_count=0)
            piece_count = 0
            for group, line in drafts:
                item = PodRipWorkItem.objects.select_for_update().get(
                    public_id=line["work_item_public_id"]
                )
                if item.status != PodRipWorkItem.Status.QUEUED:
                    raise ValidationError(
                        f"La commande {item.shopify_order_number} n'est plus en file "
                        "(annulée ou déjà en lot)."
                    )
                start = (
                    PodPickSessionLine.objects.filter(
                        work_item=item, voided_at__isnull=True
                    ).aggregate(last=Max("sequence"))["last"]
                    or 0
                )
                # sequences must stay unique even with voided rows
                absolute_start = (
                    PodPickSessionLine.objects.filter(work_item=item).aggregate(
                        last=Max("sequence")
                    )["last"]
                    or 0
                )
                start = max(start, absolute_start)
                markings = " · ".join(line["markings"])[:255]
                for offset in range(int(line["quantity"])):
                    piece_count += 1
                    PodPickSessionLine.objects.create(
                        session=session,
                        work_item=item,
                        sequence=start + offset + 1,
                        scan_identifier=new_scan_identifier(),
                        shopify_order_number=line["order_number"][:64],
                        shopify_sku=(line["shopify_sku"] or "")[:80],
                        blank_name=(group["model"] or "")[:160],
                        blank_sku=(group["variant_sku"] or "")[:80],
                        size_label=(group["size_label"] or "")[:32],
                        color_name=(group["color_name"] or "")[:64],
                        location_code=(group["location_code"] or "")[:64],
                        markings=markings,
                    )
            session.piece_count = piece_count
            session.save(update_fields=["piece_count", "updated_at"])
        record_event(
            action="pod.pick.session_opened",
            actor=actor,
            target=session,
            metadata={"source": source, "pieces": session.piece_count, "code": session.code},
        )
        return session

    def active_lines(self, session: PodPickSession):
        return session.lines.filter(voided_at__isnull=True)

    def pdf_bytes(self, *, actor, session_public_id, kind: str) -> tuple[PodPickSession, bytes]:
        from apps.pod.services.pick_sheet import write_picking_list_pdf, write_zebra_labels_pdf

        session = self.get_session(actor=actor, session_public_id=session_public_id)
        if not self.active_lines(session).exists():
            raise ValidationError(
                "Cette session n'a plus de lignes actives "
                "(commandes annulées). Réimprimez une nouvelle sélection."
            )
        if kind == "picking":
            return session, write_picking_list_pdf(session)
        if kind == "labels":
            return session, write_zebra_labels_pdf(session)
        raise ValidationError("Document de session inconnu.")
