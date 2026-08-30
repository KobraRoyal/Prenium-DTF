from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.auditlog.services import record_event
from apps.pod.models import (
    PodRipLot,
    PodRipLotFile,
    PodRipWorkItem,
    PrintTechnique,
    ShopifyVariant,
)
from apps.pod.services.documents import PodUnitDocumentService
from apps.pod.services.rip_naming import ascii_token, rip_filename
from apps.pod.services.validation import require_staff_perm, validation_message
from apps.pod.services.variant_config import VariantConfigService

MANIFEST_DIRECTORY = "00_manifest"


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
        )

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

    def prepare_dtf_lot(self, *, actor, source: str) -> PodRipLot:
        return self.prepare_lot(actor=actor, source=source, technique_code="dtf")

    def prepare_lot(self, *, actor, source: str, technique_code: str = "dtf") -> PodRipLot:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.rip.permission_rejected",
        )
        code = (technique_code or "dtf").strip().lower()
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
                queue = list(
                    PodRipWorkItem.objects.select_for_update()
                    .select_related(
                        "store",
                        "variant",
                        "variant__product",
                        "variant__ids_config__recipe",
                        "variant__ids_config__blank_variant",
                    )
                    .prefetch_related("variant__ids_config__recipe__slots__technique")
                    .filter(status=PodRipWorkItem.Status.QUEUED)
                    .order_by("created_at")
                )
                if not queue:
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
                        metadata={"source": source, "files": lot.file_count, "code": lot.code},
                    )
            if lot is None:
                raise ValidationError(
                    f"Aucun fichier {code.upper()} à exporter (file vide ou variantes NEEDS_CONFIG)."
                )
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
