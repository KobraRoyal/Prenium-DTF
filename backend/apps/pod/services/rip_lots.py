from __future__ import annotations

import logging
import shutil
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import (
    BlankVariant,
    PodPickSession,
    PodPickSessionLine,
    PodRipLot,
    PodRipLotFile,
    PodRipWorkItem,
    PodShopifyOrder,
    PodUnit,
    PrintTechnique,
    ShopifyVariant,
)
from apps.pod.services.catalog import validate_rip_directory
from apps.pod.services.documents import PodUnitDocumentService
from apps.pod.services.rip_naming import ascii_token, rip_filename
from apps.pod.services.rip_source import RipSourceService
from apps.pod.services.validation import require_staff_perm, validation_message
from apps.pod.services.variant_config import CONFIG_STATUS_NEEDS_CONFIG, VariantConfigService

logger = logging.getLogger(__name__)
_CONFIG_LABELS = {
    "pod": "Prêt à imprimer",
    "needs_config": "Mapping incomplet",
    "on_stock": "Sur stock",
    "virtual": "Virtuel",
    "unmanaged": "Non géré",
    "disabled": "Désactivé",
}


def _markings(config) -> list[str]:
    recipe = getattr(config, "recipe", None) if config is not None else None
    if recipe is None:
        return []
    labels = []
    for slot in recipe.slots.all():
        if not slot.is_enabled:
            continue
        placement = slot.get_placement_display()
        labels.append(f"{placement} · {slot.technique.name}")
    return labels


class PodRipLotService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.operate_pod_production"

    def __init__(self):
        self.variant_config_service = VariantConfigService()
        self.rip_source_service = RipSourceService()

    def nas_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / "pod_rip"

    def list_queue(self, *, actor, light: bool = False):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.rip",
            action="pod.rip.permission_rejected",
        )
        qs = PodRipWorkItem.objects.filter(status=PodRipWorkItem.Status.QUEUED)
        if light:
            # Diagnostic Lots RIP : boutique / commande / SKU seulement.
            return qs.select_related("store", "variant").order_by("created_at")
        return qs.select_related(
            "store",
            "store__customer",
            "variant",
            "variant__product",
            "variant__ids_config",
            "variant__ids_config__blank_variant",
            "variant__ids_config__blank_variant__blank",
            "variant__ids_config__recipe",
        ).prefetch_related("variant__ids_config__recipe__slots__technique")

    def production_board(
        self,
        *,
        actor,
        readiness: str = "all",
        q: str = "",
        page: int = 1,
        page_size: int = 25,
        press_page: int = 1,
    ) -> dict:
        from django.core.paginator import Paginator
        from django.db.models import Q

        del press_page  # Pose a son propre poste ; hub n’affiche qu’un compteur.
        queue = self.list_queue(actor=actor)
        query = (q or "").strip()
        if query:
            queue = queue.filter(
                Q(shopify_order_number__icontains=query) | Q(variant__sku__icontains=query)
            )
        queued_count = queue.count()
        rows = []
        ready_count = 0
        blocked_count = 0
        for item in queue:
            config = getattr(item.variant, "ids_config", None)
            status = (
                self.variant_config_service.configuration_status(config)
                if config is not None
                else CONFIG_STATUS_NEEDS_CONFIG
            )
            ready = status == "pod"
            if ready:
                ready_count += 1
            else:
                blocked_count += 1
            rows.append(
                {
                    "item": item,
                    "status": status,
                    "status_label": _CONFIG_LABELS.get(status, status),
                    "tone": "is-success" if ready else "is-warning",
                    "ready": ready,
                }
            )
        readiness_key = (readiness or "all").strip().lower()
        if readiness_key == "ready":
            filtered_rows = [row for row in rows if row["ready"]]
        elif readiness_key == "blocked":
            filtered_rows = [row for row in rows if not row["ready"]]
        else:
            readiness_key = "all"
            filtered_rows = rows

        page_obj = Paginator(filtered_rows, max(int(page_size or 25), 1)).get_page(page)
        display_rows = list(page_obj)

        skipped = list(
            PodRipWorkItem.objects.filter(
                status__in=[
                    PodRipWorkItem.Status.SKIPPED,
                    PodRipWorkItem.Status.CANCELLED,
                ]
            )
            .select_related("store", "variant")
            .only(
                "id",
                "public_id",
                "status",
                "shopify_order_number",
                "created_at",
                "store_id",
                "variant_id",
                "store__name",
                "variant__sku",
                "variant__title",
            )
            .order_by("-created_at")[:10]
        )
        # Compteur seul : la liste des pièces à poser vit sur le poste Pose.
        press_count = PodUnit.objects.filter(status=PodUnit.Status.WAITING_PRESS).count()
        # Picking groups: all ready rows matching filter (not paginated slice)
        picking_source = [row for row in filtered_rows if row["ready"]]
        picking_groups = self._picking_groups(rows=picking_source)
        pickable_count = sum(int(group.get("total_quantity") or 0) for group in picking_groups)
        return {
            "queue_rows": display_rows,
            "picking_groups": picking_groups,
            "skipped": skipped,
            "waiting_units": [],
            "queued_count": queued_count,
            "ready_count": ready_count,
            "pickable_count": pickable_count,
            "blocked_count": blocked_count,
            "skipped_count": len(skipped),
            "press_count": press_count,
            "page_obj": page_obj,
            "press_page_obj": None,
            "readiness": readiness_key,
            "q": query,
        }

    def _picking_groups(self, *, rows) -> list[dict]:
        from apps.inventory.models import ProductLocationRule, SkuKind, StockOwnerKind

        lines_by_blank: dict[str, list[dict]] = {}
        blanks: dict[str, BlankVariant] = {}
        ready_ids = [row["item"].pk for row in rows if row["ready"]]
        issued = {}
        if ready_ids:
            issued = dict(
                PodPickSessionLine.objects.filter(
                    work_item_id__in=ready_ids,
                    voided_at__isnull=True,
                )
                .values("work_item_id")
                .annotate(printed=models.Count("id"))
                .values_list("work_item_id", "printed")
            )
        for row in rows:
            if not row["ready"]:
                continue
            item = row["item"]
            remaining = int(item.quantity or 0) - int(issued.get(item.pk, 0))
            if remaining < 1:
                continue
            config = getattr(item.variant, "ids_config", None)
            blank_variant = getattr(config, "blank_variant", None) if config else None
            key = str(blank_variant.public_id) if blank_variant else ""
            if blank_variant is not None:
                blanks[key] = blank_variant
            lines_by_blank.setdefault(key, []).append(
                {
                    "order_number": item.shopify_order_number,
                    "store_name": item.store.name,
                    "shopify_sku": item.variant.sku or item.variant.title,
                    "quantity": remaining,
                    "work_item_public_id": str(item.public_id),
                    "editable": True,
                    "scan_identifier": "",
                    "markings": _markings(config),
                }
            )
        # Les unités waiting_press appartiennent au poste Pose, pas à la file picking.
        locations = {
            str(rule.blank_variant.public_id): rule.location.code
            for rule in ProductLocationRule.objects.filter(
                sku_kind=SkuKind.BLANK,
                owner_kind=StockOwnerKind.ATELIER,
                blank_variant__public_id__in=list(blanks),
                location__is_active=True,
                location__zone__is_active=True,
                location__zone__warehouse__is_active=True,
            ).select_related("location", "blank_variant")
        }
        groups = []
        for key, lines in lines_by_blank.items():
            blank_variant = blanks.get(key)
            total = sum(int(line["quantity"] or 0) for line in lines)
            if blank_variant is None:
                groups.append(
                    {
                        "model": "Support non associé",
                        "variant_sku": "",
                        "size_label": "",
                        "color_name": "",
                        "location_code": "",
                        "total_quantity": total,
                        "lines": lines,
                    }
                )
                continue
            groups.append(
                {
                    "model": blank_variant.blank.name,
                    "variant_sku": blank_variant.sku,
                    "size_label": blank_variant.size_label,
                    "color_name": blank_variant.color_name,
                    "location_code": locations.get(key, ""),
                    "total_quantity": total,
                    "lines": lines,
                }
            )
        groups.sort(
            key=lambda group: (
                group["location_code"] or "zzz",
                group["model"],
                group["variant_sku"],
            )
        )
        return groups

    def set_queued_quantity(
        self,
        *,
        actor,
        source: str,
        work_item_public_id,
        quantity,
    ) -> PodRipWorkItem:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.rip.permission_rejected",
        )
        try:
            qty = int(quantity)
        except (TypeError, ValueError) as exc:
            raise ValidationError("La quantité doit être un entier.") from exc
        if qty < 1:
            raise ValidationError("La quantité doit être au moins 1.")
        with transaction.atomic():
            item = (
                PodRipWorkItem.objects.select_for_update()
                .filter(
                    public_id=work_item_public_id,
                    status=PodRipWorkItem.Status.QUEUED,
                )
                .first()
            )
            if item is None:
                raise ValidationError("Ligne de file introuvable ou déjà traitée.")
            printed = (
                PodPickSessionLine.objects.select_for_update()
                .filter(work_item=item, voided_at__isnull=True)
                .count()
            )
            if qty < printed:
                raise ValidationError(
                    "Des étiquettes sont déjà imprimées pour cette commande. "
                    f"La quantité ne peut pas passer sous {printed}."
                )
            item.quantity = qty
            item.save(update_fields=["quantity", "updated_at"])
        record_event(
            action="pod.rip.quantity_updated",
            actor=actor,
            target=item,
            metadata={"source": source, "quantity": qty},
        )
        return item

    def list_lots(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.rip",
            action="pod.rip.permission_rejected",
        )
        return PodRipLot.objects.select_related("technique", "prepared_by").order_by(
            "-created_at"
        )[:50]

    def get_lot(self, *, actor, lot_public_id) -> PodRipLot:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.rip",
            action="pod.rip.permission_rejected",
        )
        lot = (
            PodRipLot.objects.select_related("technique", "prepared_by")
            .prefetch_related("files", "units__variant")
            .filter(public_id=lot_public_id)
            .first()
        )
        if lot is None:
            raise ValidationError("Lot RIP introuvable.")
        return lot

    def sync_lot_drive(self, *, actor, lot_public_id) -> PodRipLot:
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.rip",
            action="pod.rip.permission_rejected",
        )
        lot = self.get_lot(actor=actor, lot_public_id=lot_public_id)
        from apps.pod.services.rip_drive import PodRipDriveSyncService

        PodRipDriveSyncService().sync_lot(lot=lot, actor=actor)
        return lot

    def _enqueue_drive_sync(self, lot: PodRipLot) -> None:
        if not getattr(settings, "GOOGLE_DRIVE_SYNC_ENABLED", False):
            return
        from apps.pod.tasks import sync_pod_rip_lot_to_drive_task

        sync_pod_rip_lot_to_drive_task.delay(str(lot.public_id))

    def request_drive_sync(self, *, actor, lot_public_id) -> PodRipLot:
        """Enqueue Drive sync without loading files/units (Suivi / actions légères)."""
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.rip",
            action="pod.rip.permission_rejected",
        )
        lot = (
            PodRipLot.objects.filter(public_id=lot_public_id)
            .only("id", "public_id", "drive_synced_at", "drive_error")
            .first()
        )
        if lot is None:
            raise ValidationError("Lot RIP introuvable.")
        self._enqueue_drive_sync(lot)
        return lot

    def enqueue(
        self,
        *,
        actor,
        source: str,
        variant_public_id,
        shopify_order_number: str,
        shopify_order: PodShopifyOrder | None = None,
        shopify_line_item_id: str | None = None,
        quantity: int = 1,
        trusted_source: bool = False,
    ) -> PodRipWorkItem:
        if not trusted_source:
            require_staff_perm(
                actor,
                self.manage_permission,
                source=source,
                action="pod.rip.permission_rejected",
            )
        order_number = (shopify_order_number or "").strip()
        if not order_number:
            raise ValidationError("Le numéro de commande Shopify est obligatoire.")
        if quantity < 1:
            raise ValidationError("La quantité doit être au moins 1.")
        line_item_id = str(shopify_line_item_id or "").strip() or None
        if (shopify_order is None) != (line_item_id is None):
            raise ValidationError(
                "L'identité Shopify doit contenir la commande et la ligne ensemble."
            )
        variant = (
            ShopifyVariant.objects.select_related("product__store")
            .filter(public_id=variant_public_id)
            .first()
        )
        if variant is None:
            raise ValidationError("Variante Shopify introuvable.")
        if shopify_order is not None:
            if shopify_order.store_id != variant.product.store_id:
                raise ValidationError("La commande et la variante Shopify divergent.")
            if (
                variant.product.store.customer_id is None
                or shopify_order.customer_id != variant.product.store.customer_id
            ):
                raise ValidationError("La commande Shopify appartient à un autre Customer.")
        item = PodRipWorkItem.objects.create(
            store=variant.product.store,
            variant=variant,
            shopify_order_number=order_number,
            shopify_order=shopify_order,
            shopify_line_item_id=line_item_id,
            quantity=quantity,
        )
        record_event(
            action="pod.rip.work_item_queued",
            actor=actor,
            target=item,
            metadata={
                "source": source,
                "order": order_number,
                "order_id": shopify_order.external_order_id if shopify_order else "",
                "line_item_id": line_item_id or "",
            },
        )
        return item

    def prepare_dtf_for_pick_session(
        self,
        *,
        actor,
        session: PodPickSession,
        source: str,
    ) -> PodRipLot | None:
        existing = (
            PodRipLot.objects.filter(
                nas_relative_path=session.code,
                status=PodRipLot.Status.PREPARED,
            )
            .order_by("-prepared_at")
            .first()
        )
        if existing is not None:
            self._enqueue_drive_sync(existing)
            return existing
        work_item_public_ids = list(
            PodPickSessionLine.objects.filter(session=session, voided_at__isnull=True)
            .values_list("work_item__public_id", flat=True)
            .distinct()
        )
        if not work_item_public_ids:
            return None
        return self.prepare_dtf_lot(
            actor=actor,
            source=source,
            work_item_public_ids=[str(value) for value in work_item_public_ids],
        )

    def rip_ready_work_items_for_session(self, *, session) -> list[PodRipWorkItem]:
        if session is None:
            return []
        item_ids = {
            line.work_item_id
            for line in PodPickSessionLine.objects.filter(
                session_id=session.pk,
                voided_at__isnull=True,
            ).only("work_item_id")
        }
        if not item_ids:
            return []
        ready: list[PodRipWorkItem] = []
        for item in PodRipWorkItem.objects.filter(
            pk__in=item_ids,
            status=PodRipWorkItem.Status.QUEUED,
        ).order_by("shopify_order_number", "created_at"):
            if self._work_item_ready_for_rip_lot(item):
                ready.append(item)
        return ready

    def _work_item_ready_for_rip_lot(self, item: PodRipWorkItem) -> bool:
        """Prêt dès que les étiquettes picking existent (impression RIP avant ou après prélèvement)."""
        required = max(int(item.quantity or 0), 1)
        lines = PodPickSessionLine.objects.filter(work_item_id=item.pk, voided_at__isnull=True)
        if lines.count() < required:
            return False
        return lines.filter(unit_id__isnull=True).exists()

    def prepare_dtf_lot(
        self,
        *,
        actor,
        source: str,
        work_item_public_ids: list[str] | None = None,
    ) -> PodRipLot:
        return self.prepare_lot(
            actor=actor,
            source=source,
            technique_code="dtf",
            work_item_public_ids=work_item_public_ids,
        )

    def prepare_lot(
        self,
        *,
        actor,
        source: str,
        technique_code: str = "dtf",
        work_item_public_ids: list[str] | None = None,
    ) -> PodRipLot:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.rip.permission_rejected",
        )
        code = (technique_code or "dtf").strip().lower()
        selected: set[str] | None = None
        if work_item_public_ids is not None:
            selected = {str(value) for value in work_item_public_ids if value}
            if not selected:
                raise ValidationError("Sélectionnez au moins une commande à préparer.")
        lot_root_to_cleanup: Path | None = None
        published_paths_to_cleanup: list[Path] = []
        committed = False
        try:
            lot = None
            with transaction.atomic():
                technique = PrintTechnique.objects.filter(code=code, is_active=True).first()
                if technique is None:
                    raise ValidationError("Technique inactive ou introuvable.")
                validate_rip_directory(technique.rip_directory)
                if code == "dtf" and technique.rip_directory != "02_rip":
                    raise ValidationError("Technique DTF inactive ou répertoire RIP invalide.")
                queued = PodRipWorkItem.objects.select_for_update().filter(
                    status=PodRipWorkItem.Status.QUEUED
                )
                if selected is not None:
                    queued = queued.filter(public_id__in=selected)
                locked_ids = list(queued.order_by("created_at").values_list("pk", flat=True))
                queue = list(
                    PodRipWorkItem.objects.filter(pk__in=locked_ids)
                    .select_related(
                        "store",
                        "store__customer",
                        "variant",
                        "variant__product",
                        "variant__ids_config__recipe",
                        "variant__ids_config__blank_variant",
                    )
                    .prefetch_related(
                        "variant__ids_config__recipe__slots__technique",
                        "variant__ids_config__recipe__slots__source_asset_version__asset",
                    )
                    .order_by("created_at")
                )
                self._validate_queue_scope(queue=queue, selected=selected)
                if not queue:
                    if selected is not None:
                        raise ValidationError(
                            "Aucune commande sélectionnée n'est en file RIP prête."
                        )
                    raise ValidationError("Aucune pièce en file RIP.")
                planned = self._plan_files(queue=queue, technique=technique)
                if planned:
                    pick_session = self._resolve_pick_session_for_lot(planned=planned)
                    lot_code = self._new_lot_code()
                    # Visuels regroupés par session picking : l'opérateur lance
                    # l'impression depuis POD_RIP/<session>/<technique.rip_directory>/.
                    relative = pick_session.code
                    lot = PodRipLot.objects.create(
                        code=lot_code,
                        customer=queue[0].store.customer,
                        technique=technique,
                        nas_relative_path=relative,
                        prepared_by=actor,
                        prepared_at=timezone.now(),
                        status=PodRipLot.Status.PREPARED,
                        file_count=len(planned),
                    )
                    lot_root = self._lot_root(lot=lot)
                    session_folder_preexisted = lot_root.exists()
                    lot_root.mkdir(parents=True, exist_ok=True)
                    if not session_folder_preexisted:
                        lot_root_to_cleanup = lot_root
                    published_paths = self._write_nas_lot(lot=lot, planned=planned)
                    published_paths_to_cleanup = list(published_paths)
                    PodUnitDocumentService().create_units_for_lot(lot=lot, planned=planned)
                    published_paths_to_cleanup = []
                    for item in queue:
                        if item.status == PodRipWorkItem.Status.QUEUED:
                            item.status = PodRipWorkItem.Status.INCLUDED
                            item.save(update_fields=["status", "updated_at"])
                    record_event(
                        action="pod.rip.lot_prepared",
                        actor=actor,
                        target=lot,
                        metadata={
                            "source": source,
                            "files": lot.file_count,
                            "code": lot.code,
                            "pick_session": pick_session.code,
                            "selected_count": len(selected) if selected is not None else None,
                        },
                    )
            if lot is None:
                raise ValidationError(
                    f"Aucun fichier {code.upper()} à exporter "
                    "(file vide ou variantes NEEDS_CONFIG)."
                )
            committed = True
            self._enqueue_drive_sync(lot)
            return lot
        except ValidationError as exc:
            record_event(
                action="pod.rip.lot_prepare_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source},
            )
            raise
        finally:
            if not committed:
                for path in published_paths_to_cleanup:
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        logger.exception("Échec nettoyage fichier RIP après rollback: %s", path)
                if lot_root_to_cleanup is not None:
                    try:
                        shutil.rmtree(lot_root_to_cleanup)
                    except OSError:
                        logger.exception(
                            "Échec nettoyage du lot RIP après rollback: %s", lot_root_to_cleanup
                        )

    def _validate_queue_scope(
        self,
        *,
        queue: list[PodRipWorkItem],
        selected: set[str] | None,
    ) -> None:
        queue_public_ids = {str(item.public_id) for item in queue}
        if selected is not None and queue_public_ids != selected:
            raise ValidationError(
                "Une commande sélectionnée est introuvable, annulée ou déjà préparée."
            )
        store_ids = {item.store_id for item in queue}
        if len(store_ids) > 1:
            raise ValidationError(
                "Un lot RIP doit rester limité à une seule boutique. "
                "Préparez une boutique à la fois."
            )
        if any(item.variant.product.store_id != item.store_id for item in queue):
            raise ValidationError("La boutique de la commande et celle de la variante divergent.")
        if any(item.store.customer_id is None for item in queue):
            raise ValidationError(
                "Chaque boutique doit être liée à un Customer avant la production POD."
            )
        customer_ids = {item.store.customer_id for item in queue}
        if len(customer_ids) > 1:
            raise ValidationError("Un lot RIP ne peut pas mélanger plusieurs clients.")

    def _resolve_pick_session_for_lot(self, *, planned: list[dict]) -> PodPickSession:
        items = {entry["work_item"].pk: entry["work_item"] for entry in planned}
        lines = list(
            PodPickSessionLine.objects.select_for_update(of=("self",))
            .select_related("session")
            .filter(work_item_id__in=items, voided_at__isnull=True)
            .exclude(reservation_status=PodPickSessionLine.ReservationStatus.RELEASED)
        )
        label_counts: dict[int, int] = {}
        session_ids: set[int] = set()
        for line in lines:
            label_counts[line.work_item_id] = label_counts.get(line.work_item_id, 0) + 1
            session_ids.add(line.session_id)
        for item_id, item in items.items():
            required = max(int(item.quantity or 0), 1)
            labeled = int(label_counts.get(item_id, 0))
            if labeled < required:
                raise ValidationError(
                    f"Étiquettes picking manquantes pour {item.shopify_order_number} : "
                    f"{labeled}/{required} pièce(s). "
                    "Générez picking + Zebra avant de préparer le lot DTF."
                )
        if len(session_ids) != 1:
            raise ValidationError(
                "Un lot RIP regroupe les visuels d'une seule session picking. "
                "Sélectionnez les commandes d'une même session."
            )
        return lines[0].session

    def _plan_files(self, *, queue: list[PodRipWorkItem], technique: PrintTechnique) -> list[dict]:
        planned = []
        seen_names: set[str] = set()
        for item in queue:
            config = getattr(item.variant, "ids_config", None)
            if config is None or self.variant_config_service.configuration_status(config) != "pod":
                item.status = PodRipWorkItem.Status.SKIPPED
                item.skip_reason = "Variante non prête POD."
                item.save(update_fields=["status", "skip_reason", "updated_at"])
                continue
            slots = list(config.recipe.slots.filter(is_enabled=True, technique=technique))
            if not slots:
                item.status = PodRipWorkItem.Status.SKIPPED
                item.skip_reason = f"Aucun slot {technique.code} avec fichier HD."
                item.save(update_fields=["status", "skip_reason", "updated_at"])
                continue
            sku = item.variant.sku or config.blank_variant.sku
            for slot in slots:
                source_asset_version = self.rip_source_service.resolve(
                    slot=slot,
                    store=item.store,
                    technique=technique,
                )
                filename = rip_filename(
                    shop_slug=item.store.slug,
                    order_number=item.shopify_order_number,
                    placement=slot.placement,
                    sku=sku,
                    extension=self.rip_source_service.source_extension(
                        version=source_asset_version,
                        technique=technique,
                    ),
                )
                if filename in seen_names:
                    raise ValidationError(
                        f"Collision de nom RIP : {filename}. Ajustez boutique, SO ou SKU."
                    )
                seen_names.add(filename)
                planned.append(
                    {
                        "work_item": item,
                        "variant": item.variant,
                        "slot": slot,
                        "source_asset_version": source_asset_version,
                        "filename": filename,
                    }
                )
        return planned

    def _new_lot_code(self) -> str:
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        return f"lot-{stamp}-{ascii_token(str(timezone.now().microsecond), fallback='lot')}"

    def _lot_root(self, *, lot: PodRipLot) -> Path:
        root = self.nas_root().resolve()
        lot_root = (root / lot.nas_relative_path).resolve()
        try:
            lot_root.relative_to(root)
        except ValueError as exc:
            raise ValidationError("Chemin de lot RIP invalide.") from exc
        if lot_root == root:
            raise ValidationError("Chemin de lot RIP invalide.")
        return lot_root

    def _write_nas_lot(self, *, lot: PodRipLot, planned: list[dict]) -> list[Path]:
        """Exporte uniquement les visuels HD sous <session>/<technique.rip_directory>/."""
        lot_root = self._lot_root(lot=lot)
        rip_dir = lot_root / validate_rip_directory(lot.technique.rip_directory)
        try:
            rip_dir.resolve().relative_to(lot_root)
        except ValueError as exc:
            raise ValidationError("Répertoire RIP hors du lot.") from exc
        rip_dir.mkdir(parents=True, exist_ok=True)
        staged_entries = []
        published_paths: list[Path] = []
        try:
            for entry in planned:
                destination = rip_dir / entry["filename"]
                if destination.exists():
                    raise ValidationError(f"Collision de nom RIP : {entry['filename']}.")
                staged = self.rip_source_service.stage(
                    version=entry["source_asset_version"],
                    store=entry["work_item"].store,
                    technique=entry["slot"].technique,
                    destination=destination,
                    drive_source=entry["slot"].source_drive_hd,
                )
                staged_entries.append((entry, staged, destination))

            for entry, staged, destination in staged_entries:
                self.rip_source_service.publish(staged=staged, destination=destination)
                published_paths.append(destination)
                version = entry["source_asset_version"]
                source_name = Path((version.original_filename or "source").replace("\\", "/")).name
                PodRipLotFile.objects.create(
                    lot=lot,
                    work_item=entry["work_item"],
                    variant=entry["variant"],
                    placement=entry["slot"].placement,
                    technique=entry["slot"].technique,
                    filename=entry["filename"],
                    source_print_reference=source_name,
                    source_asset_version=version,
                    checksum_sha256=staged.checksum_sha256,
                )
            nested = [p for p in rip_dir.iterdir() if p.is_dir()]
            if nested:
                raise ValidationError(
                    f"{lot.technique.rip_directory}/ doit rester strictement plat."
                )
            return published_paths
        except Exception:
            for _entry, staged, _destination in staged_entries:
                staged.path.unlink(missing_ok=True)
            for path in published_paths:
                path.unlink(missing_ok=True)
            raise
