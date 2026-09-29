from __future__ import annotations

import base64
import hashlib

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from apps.auditlog.services import record_event
from apps.customers.models import Customer
from apps.inventory.models import WarehouseZone
from apps.inventory.services.stock_ops import StockOpsService
from apps.inventory.services.warehouse import WarehouseLayoutService
from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    BlankVariant,
    IdsVariantConfig,
    MarkingZone,
    PodPickSession,
    PodRipWorkItem,
    PodUnit,
    PrintTechnique,
)
from apps.pod.services.blank_marking_options import BlankMarkingOptionsService
from apps.pod.services.catalog import BlankCatalogService, PrintTechniqueService
from apps.pod.services.drive_hd_sources import DriveHdSourceService
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.pose import PodPoseService
from apps.pod.services.rip_lots import PodRipLotService
from apps.pod.services.validation import require_staff_perm
from apps.pod.services.variant_config import ShopifyCatalogService, VariantConfigService
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from apps.uploads.models import Asset, AssetVersion

_DEMO_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


class PodOpsBootstrapService:
    """Bootstrap démo explicite, réservé aux commandes de seed/dev."""

    manage_catalog = "pod.manage_pod_catalog"
    manage_production = "pod.operate_pod_production"
    manage_warehouse = "inventory.manage_warehouse"

    QUEUE_ORDER = "SO-SEED-QUEUE"
    PICK_ORDER = "SO-SEED-PICK"
    POSE_ORDER = "SO-SEED-POSE"
    QC_ORDER = "SO-SEED-QC"

    def __init__(self):
        self.techniques = PrintTechniqueService()
        self.blanks = BlankCatalogService()
        self.marking_options = BlankMarkingOptionsService()
        self.warehouse = WarehouseLayoutService()
        self.shopify = ShopifyCatalogService()
        self.variant_config = VariantConfigService()
        self.stock = StockOpsService()
        self.drive_hd = DriveHdSourceService()
        self.pick_sessions = PodPickSessionService()
        self.rip = PodRipLotService()
        self.pose = PodPoseService()

    def ensure_ready(self, *, actor, customer=None) -> dict:
        require_staff_perm(
            actor,
            self.manage_catalog,
            source="pod.ops_bootstrap",
            action="pod.ops_bootstrap.permission_rejected",
        )
        require_staff_perm(
            actor,
            self.manage_production,
            source="pod.ops_bootstrap",
            action="pod.ops_bootstrap.permission_rejected",
        )
        require_staff_perm(
            actor,
            self.manage_warehouse,
            source="pod.ops_bootstrap",
            action="pod.ops_bootstrap.permission_rejected",
        )
        drive_option = self._resolve_drive_hd_file(actor=actor)
        with transaction.atomic():
            self.techniques.ensure_dtf_technique(actor=actor)
            self.warehouse.ensure_default_layout(actor=actor)
            bins = self._ensure_bins(actor=actor)
            blank_variant = self._ensure_blank(actor=actor)
            product = self.shopify.ensure_demo_catalog(actor=actor)
            store = product.store
            if customer is None:
                customer = store.customer or Customer.objects.create(name="Client POD démo")
            if store.customer_id not in (None, customer.pk):
                raise ValidationError("La boutique démo est déjà liée à un autre client.")
            if store.customer_id is None:
                store.customer = customer
                store.save(update_fields=["customer", "updated_at"])
                record_event(
                    action="pod.shopify.store_customer_assigned",
                    actor=actor,
                    target=store,
                    metadata={"customer_public_id": str(customer.public_id)},
                )
            shopify_variant = product.variants.get(sku="TEE-BLK-M")
            if drive_option is not None:
                self._ensure_pod_mapping(
                    actor=actor,
                    blank_variant=blank_variant,
                    shopify_variant=shopify_variant,
                    drive_file_id=drive_option.file_id,
                    drive_filename=drive_option.name,
                )
            else:
                self._ensure_pod_mapping_local(
                    actor=actor,
                    blank_variant=blank_variant,
                    shopify_variant=shopify_variant,
                )
                self._ensure_local_demo_sources(
                    actor=actor,
                    customer=customer,
                    shopify_variant=shopify_variant,
                )
            self.warehouse.set_blank_default_location(
                actor=actor,
                source="pod_ops_bootstrap",
                variant_public_id=blank_variant.public_id,
                location_public_id=bins["blanks"].public_id,
            )
            self._ensure_qty(
                actor=actor,
                blank_variant=blank_variant,
                location=bins["blanks"],
                target_qty=20,
            )
            self._ensure_on_stock(actor=actor, product=product, location=bins["finished"])
        if drive_option is not None:
            self._ensure_drive_sources_ready(shopify_variant=shopify_variant)
        pipeline = self._ensure_production_pipeline(
            actor=actor,
            shopify_variant=shopify_variant,
            blank_variant=blank_variant,
            blanks_bin=bins["blanks"],
        )
        return {
            "blank_variant": blank_variant,
            "shopify_variant": shopify_variant,
            "bins": bins,
            "drive_hd_file": (
                {"file_id": drive_option.file_id, "name": drive_option.name}
                if drive_option is not None
                else None
            ),
            "pipeline": pipeline,
        }

    def _resolve_drive_hd_file(self, *, actor):
        result = self.drive_hd.list_options(actor=actor, refresh=True)
        if not result.configured or result.error or not result.options:
            return None
        if len(result.options) > 1:
            options = sorted(result.options, key=lambda item: (item.name.lower(), item.file_id))
            return options[0]
        return result.options[0]

    def _ensure_qty(
        self,
        *,
        actor,
        blank_variant,
        location,
        target_qty: int,
        owner_kind: str = "atelier",
        customer_public_id=None,
    ) -> None:
        from apps.inventory.models import SkuKind, StockBalance, StockOwnerKind

        owner = StockOwnerKind.CUSTOMER if owner_kind == "customer" else StockOwnerKind.ATELIER
        customer = None
        if owner == StockOwnerKind.CUSTOMER:
            customer = Customer.objects.filter(public_id=customer_public_id).first()
        balance = StockBalance.objects.filter(
            sku_kind=SkuKind.BLANK,
            blank_variant=blank_variant,
            location=location,
            owner_kind=owner,
            customer=customer,
        ).first()
        current = balance.qty_on_hand if balance else 0
        if current >= target_qty:
            return
        self.stock.receive_blank(
            actor=actor,
            source="pod_ops_bootstrap",
            blank_variant_public_id=blank_variant.public_id,
            location_public_id=location.public_id,
            quantity=target_qty - current,
            owner_kind=owner_kind,
            customer_public_id=customer_public_id,
        )

    def _ensure_bins(self, *, actor):
        zones = {zone.kind: zone for zone in self.warehouse.list_zones(actor=actor)}
        specs = (
            (WarehouseZone.Kind.BLANKS, "A-01-01-A", "Vierges allée A"),
            (WarehouseZone.Kind.RETURNS, "R-01-01-A", "Retours A"),
            (WarehouseZone.Kind.CLIENT, "C-01-01-A", "Stock client A"),
            (WarehouseZone.Kind.FINISHED, "F-01-01-A", "Finis A"),
        )
        bins = {}
        for kind, code, label in specs:
            zone = zones[kind]
            existing = zone.locations.filter(code=code).first()
            if existing:
                bins[kind] = existing
                continue
            bins[kind] = self.warehouse.create_location(
                actor=actor,
                source="pod_ops_bootstrap",
                data={
                    "zone_public_id": str(zone.public_id),
                    "code": code,
                    "label": label,
                },
            )
        return {
            "blanks": bins[WarehouseZone.Kind.BLANKS],
            "returns": bins[WarehouseZone.Kind.RETURNS],
            "client": bins[WarehouseZone.Kind.CLIENT],
            "finished": bins[WarehouseZone.Kind.FINISHED],
        }

    def _ensure_blank(self, *, actor) -> BlankVariant:
        blank = Blank.objects.filter(sku="TEE-POD").first()
        if blank is None:
            blank = self.blanks.create_blank(
                actor=actor,
                source="pod_ops_bootstrap",
                data={"sku": "TEE-POD", "name": "T-shirt POD démo", "brand": "Prenium"},
            )
        variant = BlankVariant.objects.filter(sku="TEE-POD-M").first()
        if variant is None:
            variant = self.blanks.create_variant(
                actor=actor,
                source="pod_ops_bootstrap",
                blank_public_id=blank.public_id,
                data={"sku": "TEE-POD-M", "size_label": "M", "color_name": "Noir"},
            )
        dtf = PrintTechnique.objects.get(code="dtf")
        zones = list(
            MarkingZone.objects.filter(
                code__in=("front", "left_chest", "back"),
                is_active=True,
            )
        )
        if zones:
            self.marking_options.save(
                actor=actor,
                source="pod_ops_bootstrap",
                blank_public_id=blank.public_id,
                zone_public_ids=[str(zone.public_id) for zone in zones],
                technique_public_ids=[str(dtf.public_id)],
            )
        return variant

    def _ensure_pod_mapping(
        self,
        *,
        actor,
        blank_variant,
        shopify_variant,
        drive_file_id: str,
        drive_filename: str,
    ) -> None:
        dtf = PrintTechnique.objects.get(code="dtf")
        blank = blank_variant.blank
        placements = []
        if blank.marking_options_configured:
            placements = list(
                blank.allowed_zones.filter(is_active=True)
                .order_by("display_order", "name")
                .values_list("code", flat=True)
            )
        if not placements:
            placements = ["front", "left_chest"]
        # Un seul fichier HD en bibliothèque : on le réutilise sur chaque zone autorisée.
        slots = tuple(
            VariantSlotPayload(
                placement=placement,
                technique_public_id=str(dtf.public_id),
                print_reference=drive_filename[:255],
                source_drive_file_id=drive_file_id,
                display_order=index,
            )
            for index, placement in enumerate(placements)
        )
        config = self.variant_config.save_config(
            actor=actor,
            variant_public_id=shopify_variant.public_id,
            payload=VariantConfigPayload(
                mode=IdsVariantConfig.Mode.POD,
                blank_variant_public_id=str(blank_variant.public_id),
                slots=slots,
            ),
            source="pod_ops_bootstrap",
        )
        return config

    def _ensure_pod_mapping_local(self, *, actor, blank_variant, shopify_variant) -> None:
        config = self.variant_config.get_or_create_config(shopify_variant)
        if self.variant_config.configuration_status(config) == "pod":
            return
        dtf = PrintTechnique.objects.get(code="dtf")
        self.variant_config.save_config(
            actor=actor,
            variant_public_id=shopify_variant.public_id,
            payload=VariantConfigPayload(
                mode=IdsVariantConfig.Mode.POD,
                blank_variant_public_id=str(blank_variant.public_id),
                slots=(
                    VariantSlotPayload(
                        placement=BlankPlacementCapability.Placement.FRONT,
                        technique_public_id=str(dtf.public_id),
                        print_reference="front_hd.png",
                    ),
                    VariantSlotPayload(
                        placement=BlankPlacementCapability.Placement.LEFT_CHEST,
                        technique_public_id=str(dtf.public_id),
                        print_reference="heart_hd.png",
                    ),
                ),
            ),
            source="pod_ops_bootstrap",
        )

    def _ensure_local_demo_sources(self, *, actor, customer, shopify_variant) -> None:
        config = shopify_variant.ids_config
        recipe = config.recipe
        for slot in recipe.slots.filter(is_enabled=True).select_related("source_asset_version"):
            if slot.source_asset_version_id:
                if slot.source_asset_version.customer_id != customer.pk:
                    raise ValidationError("Le visuel démo appartient à un autre client.")
                continue
            filename = f"demo-{slot.placement}.png"
            asset = Asset.objects.create(
                customer=customer,
                created_by=actor,
                name=f"Visuel POD démo {slot.get_placement_display()}",
            )
            version = AssetVersion.objects.create(
                customer=customer,
                asset=asset,
                uploaded_by=actor,
                version_number=1,
                file=ContentFile(_DEMO_PNG, name=filename),
                original_filename=filename,
                mime_type="image/png",
                size_bytes=len(_DEMO_PNG),
                sha256=hashlib.sha256(_DEMO_PNG).hexdigest(),
                analysis_status=AssetVersion.AnalysisStatus.READY,
            )
            asset.current_version = version
            asset.save(update_fields=["current_version", "updated_at"])
            slot.source_asset_version = version
            slot.print_reference = filename
            slot.save(update_fields=["source_asset_version", "print_reference", "updated_at"])

    def _ensure_drive_sources_ready(self, *, shopify_variant) -> None:
        config = getattr(shopify_variant, "ids_config", None)
        recipe = getattr(config, "recipe", None) if config is not None else None
        if recipe is None:
            return
        for slot in recipe.slots.select_related("source_drive_hd", "source_asset_version"):
            drive_source = slot.source_drive_hd
            if drive_source is None:
                continue
            if (
                drive_source.status == drive_source.Status.READY
                and drive_source.asset_version_id
                and drive_source.asset_version.analysis_status == AssetVersion.AnalysisStatus.READY
            ):
                if slot.source_asset_version_id != drive_source.asset_version_id:
                    slot.source_asset_version = drive_source.asset_version
                    slot.print_reference = (drive_source.original_filename or slot.print_reference)[
                        :255
                    ]
                    slot.save(
                        update_fields=["source_asset_version", "print_reference", "updated_at"]
                    )
                continue
            result = self.drive_hd.import_source(source_public_id=str(drive_source.public_id))
            if not result.get("ok") or result.get("status") != drive_source.Status.READY:
                raise ValidationError(
                    "Import Drive HD seed échoué : "
                    f"{result.get('error') or result.get('status') or 'inconnu'}."
                )
            drive_source.refresh_from_db()
            slot.source_asset_version = drive_source.asset_version
            slot.print_reference = (drive_source.original_filename or slot.print_reference)[:255]
            slot.save(update_fields=["source_asset_version", "print_reference", "updated_at"])

    def _ensure_on_stock(self, *, actor, product, location) -> None:
        from apps.inventory.models import SkuKind, StockBalance, StockOwnerKind

        variant = product.variants.get(sku="TEE-WHT-M")
        config = self.variant_config.get_or_create_config(variant)
        if self.variant_config.configuration_status(config) != "on_stock":
            self.variant_config.save_config(
                actor=actor,
                variant_public_id=variant.public_id,
                payload=VariantConfigPayload(
                    mode=IdsVariantConfig.Mode.ON_STOCK,
                    finished_sku="TEE-WHT-M-FIN",
                ),
                source="pod_ops_bootstrap",
            )
        balance = StockBalance.objects.filter(
            sku_kind=SkuKind.FINISHED,
            finished_sku="TEE-WHT-M-FIN",
            location=location,
            owner_kind=StockOwnerKind.ATELIER,
            customer=None,
        ).first()
        current = balance.qty_on_hand if balance else 0
        if current >= 5:
            return
        self.stock.receive_finished(
            actor=actor,
            source="pod_ops_bootstrap",
            finished_sku="TEE-WHT-M-FIN",
            location_public_id=location.public_id,
            quantity=5 - current,
        )

    def _enqueue_order(self, *, actor, shopify_variant, order_number: str, quantity: int):
        existing = (
            PodRipWorkItem.objects.filter(shopify_order_number=order_number)
            .exclude(status=PodRipWorkItem.Status.CANCELLED)
            .first()
        )
        if existing is not None:
            return existing
        return self.rip.enqueue(
            actor=actor,
            source="pod_ops_bootstrap",
            variant_public_id=shopify_variant.public_id,
            shopify_order_number=order_number,
            quantity=quantity,
        )

    def _active_pick_session(self, work_item) -> PodPickSession | None:
        return (
            PodPickSession.objects.filter(
                lines__work_item=work_item,
                lines__voided_at__isnull=True,
            )
            .distinct()
            .order_by("-created_at")
            .first()
        )

    def _ensure_pick_session(self, *, actor, work_item) -> PodPickSession | None:
        existing = self._active_pick_session(work_item)
        if existing is not None:
            return existing
        if work_item.status != PodRipWorkItem.Status.QUEUED:
            return None
        return self.pick_sessions.open_session(
            actor=actor,
            source="pod_ops_bootstrap",
            work_item_public_ids=[str(work_item.public_id)],
        )

    def _advance_through_rip(
        self,
        *,
        actor,
        work_item,
        blanks_bin,
    ) -> list:
        units = list(
            PodUnit.objects.filter(work_item=work_item).exclude(status=PodUnit.Status.ISSUE)
        )
        if units:
            return units
        if work_item.status != PodRipWorkItem.Status.QUEUED:
            return []
        session = self._ensure_pick_session(actor=actor, work_item=work_item)
        if session is None:
            return []
        for line in session.lines.filter(voided_at__isnull=True, work_item=work_item):
            self.pick_sessions.confirm_pick(
                actor=actor,
                source="pod_ops_bootstrap",
                scan_identifier=line.scan_identifier,
                scanned_bin_code=blanks_bin.code,
            )
        work_item.refresh_from_db()
        if work_item.status == PodRipWorkItem.Status.QUEUED:
            self.rip.prepare_dtf_lot(
                actor=actor,
                source="pod_ops_bootstrap",
                work_item_public_ids=[str(work_item.public_id)],
            )
        from apps.pod.services.operate_workflow import PodOperateWorkflowService

        PodOperateWorkflowService().confirm_dtf_print(
            actor=actor,
            session=session,
            source="pod_ops_bootstrap",
        )
        return list(
            PodUnit.objects.filter(work_item=work_item).exclude(status=PodUnit.Status.ISSUE)
        )

    def _ensure_production_pipeline(
        self,
        *,
        actor,
        shopify_variant,
        blank_variant,
        blanks_bin,
    ) -> dict:
        queue_item = self._enqueue_order(
            actor=actor,
            shopify_variant=shopify_variant,
            order_number=self.QUEUE_ORDER,
            quantity=2,
        )
        pick_item = self._enqueue_order(
            actor=actor,
            shopify_variant=shopify_variant,
            order_number=self.PICK_ORDER,
            quantity=1,
        )
        pose_item = self._enqueue_order(
            actor=actor,
            shopify_variant=shopify_variant,
            order_number=self.POSE_ORDER,
            quantity=1,
        )
        qc_item = self._enqueue_order(
            actor=actor,
            shopify_variant=shopify_variant,
            order_number=self.QC_ORDER,
            quantity=1,
        )

        reserved_session = self._ensure_pick_session(actor=actor, work_item=pick_item)
        pose_units = self._advance_through_rip(
            actor=actor,
            work_item=pose_item,
            blanks_bin=blanks_bin,
        )
        qc_units = self._advance_through_rip(
            actor=actor,
            work_item=qc_item,
            blanks_bin=blanks_bin,
        )
        for unit in qc_units:
            if unit.status == PodUnit.Status.WAITING_PRESS:
                self.pose.mark_pressed(
                    actor=actor,
                    scan_identifier=unit.scan_identifier,
                    source="pod_ops_bootstrap",
                )

        return {
            "queue_order": queue_item.shopify_order_number,
            "pick_session": reserved_session.code if reserved_session else None,
            "pose_units": [
                unit.scan_identifier
                for unit in PodUnit.objects.filter(work_item=pose_item).order_by("sequence")
            ],
            "qc_units": [
                unit.scan_identifier
                for unit in PodUnit.objects.filter(work_item=qc_item).order_by("sequence")
            ],
            "open_sessions": PodPickSession.objects.count(),
        }
