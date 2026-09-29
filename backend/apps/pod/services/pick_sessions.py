from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.inventory.services.reservations import BlankStockReservationService
from apps.pod.models import PodPickSession, PodPickSessionLine, PodRipWorkItem
from apps.pod.services.documents import new_scan_identifier
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.validation import require_staff_perm


class PodPickSessionService:
    manage_permission = "pod.operate_pod_production"
    view_permission = "pod.access_pod_atelier"

    def __init__(self):
        self.reservations = BlankStockReservationService()

    def list_recent(self, *, actor, limit: int = 8):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.pick",
            action="pod.pick.permission_rejected",
        )
        sessions = list(PodPickSession.objects.prefetch_related("lines").all()[:limit])
        for session in sessions:
            active = [line for line in session.lines.all() if line.voided_at is None]
            session.active_lines_for_display = active
            session.active_piece_count = len(active)
            session.reserved_piece_count = sum(
                line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED
                for line in active
            )
            session.picked_piece_count = sum(
                line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED
                for line in active
            )
            session.untracked_piece_count = sum(
                line.reservation_status == PodPickSessionLine.ReservationStatus.UNTRACKED
                for line in active
            )
            session.can_reissue_legacy = bool(active) and session.untracked_piece_count == len(
                active
            )
            session.is_voided = not active and session.piece_count > 0
        return sessions

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

    def reissue_legacy_session(self, *, actor, source: str, session_public_id) -> int:
        """Soft-void pre-reservation labels so staff can reserve and print afresh."""
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.pick.permission_rejected",
        )
        with transaction.atomic():
            session = PodPickSession.objects.select_for_update(of=("self",)).filter(
                public_id=session_public_id
            ).first()
            if session is None:
                raise ValidationError("Session de picking introuvable.")
            lines = list(
                PodPickSessionLine.objects.select_for_update(of=("self",))
                .select_related("work_item")
                .filter(session=session, voided_at__isnull=True)
            )
            if not lines:
                raise ValidationError("Cette session ne contient aucune ligne active à réimprimer.")
            if any(
                line.reservation_status != PodPickSessionLine.ReservationStatus.UNTRACKED
                or line.unit_id is not None
                or line.work_item.status != PodRipWorkItem.Status.QUEUED
                for line in lines
            ):
                raise ValidationError(
                    "Reprise impossible : seules les anciennes lignes non réservées, "
                    "encore en file et non liées à une unité peuvent être réimprimées."
                )
            now = timezone.now()
            for line in lines:
                line.voided_at = now
                line.save(update_fields=["voided_at", "updated_at"])
            record_event(
                action="pod.pick.legacy_session_reissued",
                actor=actor,
                target=session,
                metadata={"source": source, "voided_count": len(lines)},
            )
            return len(lines)

    def void_lines_for_work_item(self, *, work_item: PodRipWorkItem, reason: str = "") -> int:
        now = timezone.now()
        released = 0
        picked_preserved = 0
        with transaction.atomic():
            lines = list(
                PodPickSessionLine.objects.select_for_update(of=("self",))
                .select_related("stock_balance")
                .filter(work_item=work_item, voided_at__isnull=True)
            )
            for line in lines:
                update_fields = ["voided_at", "updated_at"]
                line.voided_at = now
                if line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED:
                    if line.stock_balance_id is None:
                        raise ValidationError("Ligne réservée sans balance de stock.")
                    self.reservations.release_atelier_reservation(
                        actor=None,
                        source="pod.pick.void",
                        balance_public_id=line.stock_balance.public_id,
                        reason=reason,
                    )
                    line.reservation_status = PodPickSessionLine.ReservationStatus.RELEASED
                    line.released_at = now
                    line.released_by = None
                    update_fields.extend(
                        ["reservation_status", "released_at", "released_by"]
                    )
                    released += 1
                elif line.reservation_status == PodPickSessionLine.ReservationStatus.UNTRACKED:
                    line.reservation_status = PodPickSessionLine.ReservationStatus.RELEASED
                    line.released_at = now
                    update_fields.extend(["reservation_status", "released_at"])
                elif line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED:
                    picked_preserved += 1
                line.save(update_fields=update_fields)
            updated = len(lines)
        if updated:
            record_event(
                action="pod.pick.lines_voided",
                target=work_item,
                metadata={
                    "count": updated,
                    "released": released,
                    "picked_preserved": picked_preserved,
                    "reason": reason[:120],
                },
            )
        return updated

    def confirm_pick(
        self,
        *,
        actor,
        source: str,
        scan_identifier: str,
        scanned_bin_code: str,
    ) -> PodPickSessionLine:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.pick.permission_rejected",
        )
        scan = (scan_identifier or "").strip().upper()
        if not scan:
            raise ValidationError("Scan de l'étiquette pièce obligatoire.")
        bin_code = (scanned_bin_code or "").strip().upper()
        if not bin_code:
            raise ValidationError("Scan du bin obligatoire (POD-17).")
        with transaction.atomic():
            line = (
                PodPickSessionLine.objects.select_for_update(of=("self",))
                .select_related("stock_balance", "stock_balance__location")
                .filter(scan_identifier__iexact=scan)
                .first()
            )
            if line is None:
                raise ValidationError("Pièce de picking introuvable.")
            if line.voided_at is not None:
                raise ValidationError("Cette pièce a été annulée.")
            if line.stock_balance_id is not None:
                expected_bin = line.stock_balance.location.code.upper()
                if expected_bin != bin_code:
                    raise ValidationError(
                        f"Bin incorrect : scannez {expected_bin} pour cette pièce."
                    )
            if line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED:
                return line
            if line.reservation_status != PodPickSessionLine.ReservationStatus.RESERVED:
                raise ValidationError("Cette pièce ne porte aucune réservation active.")
            if line.stock_balance_id is None:
                raise ValidationError("Réservation de stock introuvable pour cette pièce.")
            self.reservations.consume_atelier_reservation(
                actor=actor,
                source=source,
                balance_public_id=line.stock_balance.public_id,
                scanned_bin_code=bin_code,
                note=f"POD pick line {line.public_id}",
            )
            line.reservation_status = PodPickSessionLine.ReservationStatus.PICKED
            line.picked_at = timezone.now()
            line.picked_by = actor
            line.save(
                update_fields=["reservation_status", "picked_at", "picked_by", "updated_at"]
            )
            record_event(
                action="pod.pick.line_picked",
                actor=actor,
                target=line,
                metadata={
                    "source": source,
                    "bin": line.stock_balance.location.code,
                    "work_item_public_id": str(line.work_item.public_id),
                },
            )
            return line

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
        draft_ids = {line["work_item_public_id"] for _group, line in drafts}
        if draft_ids != selected:
            raise ValidationError(
                "Une commande sélectionnée est introuvable, non prête ou déjà étiquetée."
            )
        code = f"PICK-{timezone.now():%y%m%d}-{uuid.uuid4().hex[:4].upper()}"
        with transaction.atomic():
            locked_items = {
                str(item.public_id): item
                for item in PodRipWorkItem.objects.select_for_update(of=("self",))
                .select_related(
                    "store__customer",
                    "variant__product",
                    "variant__ids_config__blank_variant",
                )
                .filter(public_id__in=selected)
            }
            if set(locked_items) != selected:
                raise ValidationError("Une commande sélectionnée est introuvable.")
            if any(item.status != PodRipWorkItem.Status.QUEUED for item in locked_items.values()):
                raise ValidationError("Une commande sélectionnée n'est plus en file RIP.")
            store_ids = {item.store_id for item in locked_items.values()}
            if len(store_ids) != 1:
                raise ValidationError(
                    "Une session de picking doit rester limitée à une seule boutique."
                )
            if any(
                item.variant.product.store_id != item.store_id
                for item in locked_items.values()
            ):
                raise ValidationError(
                    "La boutique de la commande et celle de la variante divergent."
                )
            if any(item.store.customer_id is None for item in locked_items.values()):
                raise ValidationError(
                    "Chaque boutique doit être liée à un Customer avant le picking POD."
                )
            customer_ids = {item.store.customer_id for item in locked_items.values()}
            if len(customer_ids) != 1:
                raise ValidationError("Une session de picking ne peut pas mélanger des clients.")
            session = PodPickSession.objects.create(
                code=code,
                customer_id=customer_ids.pop(),
                created_by=actor,
                piece_count=0,
            )
            piece_count = 0
            for group, line in drafts:
                item = locked_items[line["work_item_public_id"]]
                active_lines = PodPickSessionLine.objects.filter(
                    work_item=item, voided_at__isnull=True
                )
                requested_quantity = int(line["quantity"])
                if active_lines.count() + requested_quantity > int(item.quantity or 0):
                    raise ValidationError(
                        f"La commande {item.shopify_order_number} est déjà réservée "
                        "dans une autre session."
                    )
                start = active_lines.aggregate(last=Max("sequence"))["last"] or 0
                # sequences must stay unique even with voided rows
                absolute_start = (
                    PodPickSessionLine.objects.filter(work_item=item).aggregate(
                        last=Max("sequence")
                    )["last"]
                    or 0
                )
                start = max(start, absolute_start)
                markings = " · ".join(line["markings"])[:255]
                config = getattr(item.variant, "ids_config", None)
                blank_variant = getattr(config, "blank_variant", None) if config else None
                if blank_variant is None:
                    raise ValidationError(
                        f"La commande {item.shopify_order_number} n'a aucun blank configuré."
                    )
                for offset in range(requested_quantity):
                    piece_count += 1
                    balance = self.reservations.reserve_atelier_blank(
                        actor=actor,
                        source=source,
                        blank_variant=blank_variant,
                        location_code=group["location_code"],
                    )
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
                        reservation_status=PodPickSessionLine.ReservationStatus.RESERVED,
                        stock_balance=balance,
                        reserved_at=timezone.now(),
                        reserved_by=actor,
                    )
            session.piece_count = piece_count
            session.save(update_fields=["piece_count", "updated_at"])
        record_event(
            action="pod.pick.session_opened",
            actor=actor,
            target=session,
            metadata={"source": source, "pieces": session.piece_count, "code": session.code},
        )
        if getattr(settings, "POD_AUTO_RIP_ON_PICK_SESSION", True):
            session_public_id = str(session.public_id)
            actor_id = actor.pk

            def _enqueue_rip_and_drive() -> None:
                from apps.pod.tasks import prepare_pick_session_rip_and_drive_task

                prepare_pick_session_rip_and_drive_task.delay(
                    session_public_id=session_public_id,
                    actor_id=actor_id,
                )

            transaction.on_commit(_enqueue_rip_and_drive)
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
