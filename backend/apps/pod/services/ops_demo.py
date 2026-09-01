from __future__ import annotations

from django.db import transaction

from apps.inventory.models import WarehouseZone
from apps.inventory.services.stock_ops import StockOpsService
from apps.inventory.services.warehouse import WarehouseLayoutService
from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    BlankVariant,
    IdsVariantConfig,
    PrintTechnique,
)
from apps.pod.services.catalog import BlankCatalogService, PrintTechniqueService
from apps.pod.services.validation import require_staff_perm
from apps.pod.services.variant_config import ShopifyCatalogService, VariantConfigService
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload


class PodOpsBootstrapService:
    """Données démo idempotentes pour un parcours atelier POD utilisable."""

    manage_catalog = "pod.manage_pod_catalog"
    manage_warehouse = "inventory.manage_warehouse"

    def __init__(self):
        self.techniques = PrintTechniqueService()
        self.blanks = BlankCatalogService()
        self.warehouse = WarehouseLayoutService()
        self.shopify = ShopifyCatalogService()
        self.variant_config = VariantConfigService()
        self.stock = StockOpsService()

    def ensure_ready(self, *, actor, customer=None) -> dict:
        require_staff_perm(
            actor,
            self.manage_catalog,
            source="pod.ops_bootstrap",
            action="pod.ops_bootstrap.permission_rejected",
        )
        require_staff_perm(
            actor,
            self.manage_warehouse,
            source="pod.ops_bootstrap",
            action="pod.ops_bootstrap.permission_rejected",
        )
        with transaction.atomic():
            self.techniques.ensure_dtf_technique(actor=actor)
            self.warehouse.ensure_default_layout(actor=actor)
            bins = self._ensure_bins(actor=actor)
            blank_variant = self._ensure_blank(actor=actor)
            product = self.shopify.ensure_demo_catalog(actor=actor)
            shopify_variant = product.variants.get(sku="TEE-BLK-M")
            self._ensure_pod_mapping(
                actor=actor, blank_variant=blank_variant, shopify_variant=shopify_variant
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
                target_qty=10,
            )
            if customer is not None:
                self._ensure_qty(
                    actor=actor,
                    blank_variant=blank_variant,
                    location=bins["client"],
                    target_qty=3,
                    owner_kind="customer",
                    customer_public_id=customer.public_id,
                )
            self._ensure_on_stock(actor=actor, product=product, location=bins["finished"])
            self._ensure_demo_queue(actor=actor, shopify_variant=shopify_variant)
            return {
                "blank_variant": blank_variant,
                "shopify_variant": shopify_variant,
                "bins": bins,
            }

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
            from apps.customers.models import Customer

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
        for placement, required in (
            (BlankPlacementCapability.Placement.FRONT, True),
            (BlankPlacementCapability.Placement.LEFT_CHEST, False),
        ):
            if not blank.placement_capabilities.filter(placement=placement, technique=dtf).exists():
                self.blanks.add_capability(
                    actor=actor,
                    source="pod_ops_bootstrap",
                    blank_public_id=blank.public_id,
                    data={
                        "placement": placement,
                        "technique_public_id": str(dtf.public_id),
                        "is_required": required,
                    },
                )
        return variant

    def _ensure_pod_mapping(self, *, actor, blank_variant, shopify_variant) -> None:
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

    def _ensure_demo_queue(self, *, actor, shopify_variant) -> None:
        from apps.pod.models import PodRipWorkItem
        from apps.pod.services.rip_lots import PodRipLotService

        if PodRipWorkItem.objects.filter(status=PodRipWorkItem.Status.QUEUED).exists():
            return
        PodRipLotService().enqueue(
            actor=actor,
            source="pod_ops_bootstrap",
            variant_public_id=shopify_variant.public_id,
            shopify_order_number="SO-DEMO-001",
            quantity=1,
        )
