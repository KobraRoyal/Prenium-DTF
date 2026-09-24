from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import (
    BlankVariant,
    PodRipLot,
    PodRipLotFile,
    PodRipWorkItem,
    PodUnit,
    PrintTechnique,
    ShopifyVariant,
)
from apps.pod.services.documents import PodUnitDocumentService
from apps.pod.services.rip_naming import ascii_token, rip_filename
from apps.pod.services.validation import require_staff_perm, validation_message
from apps.pod.services.variant_config import CONFIG_STATUS_NEEDS_CONFIG, VariantConfigService

MANIFEST_DIRECTORY = "00_manifest"
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
    manage_permission = "pod.manage_pod_catalog"

    def __init__(self):
        self.variant_config_service = VariantConfigService()

    def nas_root(self) -> Path:
        return Path(settings.MEDIA_ROOT) / "pod_rip"

    def list_queue(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.rip",
            action="pod.rip.permission_rejected",
        )
        return PodRipWorkItem.objects.filter(status=PodRipWorkItem.Status.QUEUED).select_related(
            "store",
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
            .order_by("-created_at")[:20]
        )
        waiting_qs = (
            PodUnit.objects.filter(status=PodUnit.Status.WAITING_PRESS)
            .select_related(
                "work_item",
                "work_item__store",
                "variant",
                "variant__ids_config",
                "variant__ids_config__blank_variant",
                "variant__ids_config__blank_variant__blank",
                "variant__ids_config__recipe",
                "lot",
            )
            .prefetch_related("variant__ids_config__recipe__slots__technique")
            .order_by("created_at")
        )
        press_count = waiting_qs.count()
        press_page_obj = Paginator(waiting_qs, max(int(page_size or 25), 1)).get_page(press_page)
        waiting_units = list(press_page_obj)
        # Picking groups: all ready rows matching filter (not paginated slice)
        picking_source = [row for row in filtered_rows if row["ready"]]
        picking_groups = self._picking_groups(rows=picking_source, waiting_units=waiting_units)
        return {
            "queue_rows": display_rows,
            "picking_groups": picking_groups,
            "skipped": skipped,
            "waiting_units": waiting_units,
            "queued_count": queued_count,
            "ready_count": ready_count,
            "blocked_count": blocked_count,
            "skipped_count": len(skipped),
            "press_count": press_count,
            "page_obj": page_obj,
            "press_page_obj": press_page_obj,
            "readiness": readiness_key,
            "q": query,
        }

    def _picking_groups(self, *, rows, waiting_units) -> list[dict]:
        from apps.inventory.models import ProductLocationRule, SkuKind, StockOwnerKind

        lines_by_blank: dict[str, list[dict]] = {}
        blanks: dict[str, BlankVariant] = {}
        ready_ids = [row["item"].pk for row in rows if row["ready"]]
        issued = {}
        if ready_ids:
            from apps.pod.models import PodPickSessionLine

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
        for unit in waiting_units:
            config = getattr(unit.variant, "ids_config", None)
            blank_variant = getattr(config, "blank_variant", None) if config else None
            key = str(blank_variant.public_id) if blank_variant else ""
            if blank_variant is not None:
                blanks[key] = blank_variant
            lines_by_blank.setdefault(key, []).append(
                {
                    "order_number": unit.work_item.shopify_order_number,
                    "store_name": unit.work_item.store.name,
                    "shopify_sku": unit.variant.sku or unit.variant.title,
                    "quantity": 1,
                    "work_item_public_id": "",
                    "editable": False,
                    "scan_identifier": unit.scan_identifier,
                    "markings": _markings(config),
                }
            )
        locations = {
            str(rule.blank_variant.public_id): rule.location.code
            for rule in ProductLocationRule.objects.filter(
                sku_kind=SkuKind.BLANK,
                owner_kind=StockOwnerKind.ATELIER,
                blank_variant__public_id__in=list(blanks),
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
        item = PodRipWorkItem.objects.filter(
            public_id=work_item_public_id,
            status=PodRipWorkItem.Status.QUEUED,
        ).first()
        if item is None:
            raise ValidationError("Ligne de file introuvable ou déjà traitée.")
        printed = item.pick_lines.filter(voided_at__isnull=True).count()
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
        return PodRipLot.objects.select_related("technique", "prepared_by").prefetch_related(
            "files"
        )

    def get_lot(self, *, actor, lot_public_id) -> PodRipLot:
        lot = self.list_lots(actor=actor).filter(public_id=lot_public_id).first()
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

    def enqueue(
        self,
        *,
        actor,
        source: str,
        variant_public_id,
        shopify_order_number: str,
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
        variant = (
            ShopifyVariant.objects.select_related("product__store")
            .filter(public_id=variant_public_id)
            .first()
        )
        if variant is None:
            raise ValidationError("Variante Shopify introuvable.")
        item = PodRipWorkItem.objects.create(
            store=variant.product.store,
            variant=variant,
            shopify_order_number=order_number,
            quantity=quantity,
        )
        record_event(
            action="pod.rip.work_item_queued",
            actor=actor,
            target=item,
            metadata={"source": source, "order": order_number},
        )
        return item

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
        try:
            lot = None
            with transaction.atomic():
                technique = PrintTechnique.objects.filter(code=code, is_active=True).first()
                if technique is None:
                    raise ValidationError("Technique inactive ou introuvable.")
                if not technique.rip_directory.startswith("02_"):
                    raise ValidationError("Répertoire RIP invalide (doit commencer par 02_).")
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
                        "variant",
                        "variant__product",
                        "variant__ids_config__recipe",
                        "variant__ids_config__blank_variant",
                    )
                    .prefetch_related("variant__ids_config__recipe__slots__technique")
                    .order_by("created_at")
                )
                if not queue:
                    if selected is not None:
                        raise ValidationError(
                            "Aucune commande sélectionnée n'est en file RIP prête."
                        )
                    raise ValidationError("Aucune pièce en file RIP.")
                planned = self._plan_files(queue=queue, technique=technique)
                if planned:
                    lot_code = self._new_lot_code()
                    relative = f"{timezone.now().strftime('%Y/%m/%d')}/{lot_code}"
                    lot = PodRipLot.objects.create(
                        code=lot_code,
                        technique=technique,
                        nas_relative_path=relative,
                        prepared_by=actor,
                        prepared_at=timezone.now(),
                        status=PodRipLot.Status.PREPARED,
                        file_count=len(planned),
                    )
                    self._write_nas_lot(lot=lot, planned=planned)
                    PodUnitDocumentService().create_units_for_lot(lot=lot, planned=planned)
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
                            "selected_count": len(selected) if selected is not None else None,
                        },
                    )
            if lot is None:
                raise ValidationError(
                    f"Aucun fichier {code.upper()} à exporter "
                    "(file vide ou variantes NEEDS_CONFIG)."
                )
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
            slots = [
                slot
                for slot in config.recipe.slots.filter(is_enabled=True, technique=technique)
                if slot.print_reference.strip()
            ]
            if not slots:
                item.status = PodRipWorkItem.Status.SKIPPED
                item.skip_reason = f"Aucun slot {technique.code} avec fichier HD."
                item.save(update_fields=["status", "skip_reason", "updated_at"])
                continue
            sku = item.variant.sku or config.blank_variant.sku
            for slot in slots:
                filename = rip_filename(
                    shop_slug=item.store.slug,
                    order_number=item.shopify_order_number,
                    placement=slot.placement,
                    sku=sku,
                    extension=technique.export_extension,
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
                        "filename": filename,
                    }
                )
        return planned

    def _new_lot_code(self) -> str:
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        return f"lot-{stamp}-{ascii_token(str(timezone.now().microsecond), fallback='lot')}"

    def _write_nas_lot(self, *, lot: PodRipLot, planned: list[dict]) -> None:
        lot_root = self.nas_root() / lot.nas_relative_path
        rip_dir = lot_root / lot.technique.rip_directory
        manifest_dir = lot_root / MANIFEST_DIRECTORY
        rip_dir.mkdir(parents=True, exist_ok=True)
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_files = []
        for entry in planned:
            dest = rip_dir / entry["filename"]
            if dest.exists():
                raise ValidationError(f"Collision de nom RIP : {entry['filename']}.")
            payload = (
                f"print_reference={entry['slot'].print_reference}\n"
                f"variant={entry['variant'].public_id}\n"
                f"order={entry['work_item'].shopify_order_number}\n"
            ).encode()
            dest.write_bytes(payload)
            checksum = hashlib.sha256(payload).hexdigest()
            PodRipLotFile.objects.create(
                lot=lot,
                work_item=entry["work_item"],
                variant=entry["variant"],
                placement=entry["slot"].placement,
                technique=entry["slot"].technique,
                filename=entry["filename"],
                source_print_reference=entry["slot"].print_reference,
                checksum_sha256=checksum,
            )
            manifest_files.append(
                {
                    "filename": entry["filename"],
                    "placement": entry["slot"].placement,
                    "technique": entry["slot"].technique.code,
                    "shopify_order": entry["work_item"].shopify_order_number,
                    "shop_slug": entry["work_item"].store.slug,
                    "variant_public_id": str(entry["variant"].public_id),
                    "sku": entry["variant"].sku,
                    "source_print_reference": entry["slot"].print_reference,
                    "checksum_sha256": checksum,
                }
            )
        manifest = {
            "lot_code": lot.code,
            "technique": lot.technique.code,
            "rip_directory": lot.technique.rip_directory,
            "flat": True,
            "files": manifest_files,
        }
        (manifest_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        nested = [p for p in rip_dir.iterdir() if p.is_dir()]
        if nested:
            raise ValidationError(f"{lot.technique.rip_directory}/ doit rester strictement plat.")
