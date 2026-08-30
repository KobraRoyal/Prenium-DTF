from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.auditlog.services import record_event
from apps.pod.models import (
    BlankVariant,
    IdsVariantConfig,
    PodRecipe,
    PodRecipeSlot,
    PodRecipeTemplate,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.validation import clean_sku, require_staff_perm, validation_message
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload

CONFIG_STATUS_UNMANAGED = "unmanaged"
CONFIG_STATUS_DISABLED = "disabled"
CONFIG_STATUS_VIRTUAL = "virtual"
CONFIG_STATUS_ON_STOCK = "on_stock"
CONFIG_STATUS_POD = "pod"
CONFIG_STATUS_NEEDS_CONFIG = "needs_config"


class ShopifyCatalogService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.manage_pod_catalog"

    def list_stores(self, *, actor):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.catalogue",
            action="pod.catalogue.permission_rejected",
        )
        return ShopifyStore.objects.filter(is_active=True)

    def list_products(self, *, actor, store_public_id=None):
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.catalogue",
            action="pod.catalogue.permission_rejected",
        )
        qs = ShopifyProduct.objects.select_related("store").prefetch_related(
            "variants__ids_config__recipe__slots__technique",
            "variants__ids_config__blank_variant",
        )
        if store_public_id:
            qs = qs.filter(store__public_id=store_public_id)
        return qs.order_by("store__name", "title")

    def get_product(self, *, actor, product_public_id) -> ShopifyProduct:
        product = self.list_products(actor=actor).filter(public_id=product_public_id).first()
        if product is None:
            raise ValidationError("Produit Shopify introuvable.")
        return product

    def get_variant(self, *, actor, variant_public_id) -> ShopifyVariant:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.catalogue",
            action="pod.catalogue.permission_rejected",
        )
        variant = (
            ShopifyVariant.objects.select_related(
                "product",
                "product__store",
                "ids_config__blank_variant__blank",
                "ids_config__recipe",
            )
            .prefetch_related(
                "ids_config__recipe__slots__technique",
                "ids_config__blank_variant__blank__placement_capabilities__technique",
            )
            .filter(public_id=variant_public_id)
            .first()
        )
        if variant is None:
            raise ValidationError("Variante Shopify introuvable.")
        return variant

    @transaction.atomic
    def ensure_demo_catalog(self, *, actor) -> ShopifyProduct:
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.catalogue",
            action="pod.catalogue.permission_rejected",
        )
        store, _ = ShopifyStore.objects.get_or_create(
            slug="demo-boutique",
            defaults={
                "name": "Boutique démo",
                "shop_domain": "demo-boutique.myshopify.com",
            },
        )
        product, _ = ShopifyProduct.objects.get_or_create(
            store=store,
            external_id="gid://shopify/Product/1001",
            defaults={"title": "T-shirt unisexe", "handle": "tee-unisex"},
        )
        for external_id, title, sku in (
            ("gid://shopify/ProductVariant/2001", "Noir / S", "TEE-BLK-S"),
            ("gid://shopify/ProductVariant/2002", "Noir / M", "TEE-BLK-M"),
            ("gid://shopify/ProductVariant/2003", "Blanc / M", "TEE-WHT-M"),
        ):
            variant, created = ShopifyVariant.objects.get_or_create(
                product=product,
                external_id=external_id,
                defaults={"title": title, "sku": sku},
            )
            if created:
                IdsVariantConfig.objects.create(variant=variant)
        return product


class VariantConfigService:
    view_permission = "pod.access_pod_atelier"
    manage_permission = "pod.manage_pod_catalog"

    def get_or_create_config(self, variant: ShopifyVariant) -> IdsVariantConfig:
        config, _created = IdsVariantConfig.objects.get_or_create(variant=variant)
        return config

    def configuration_status(self, config: IdsVariantConfig) -> str:
        if config.mode == IdsVariantConfig.Mode.UNMANAGED:
            return CONFIG_STATUS_UNMANAGED
        if config.mode == IdsVariantConfig.Mode.DISABLED:
            return CONFIG_STATUS_DISABLED
        if config.mode == IdsVariantConfig.Mode.VIRTUAL:
            return CONFIG_STATUS_VIRTUAL
        if config.mode == IdsVariantConfig.Mode.ON_STOCK:
            return (
                CONFIG_STATUS_ON_STOCK
                if config.finished_sku
                else CONFIG_STATUS_NEEDS_CONFIG
            )
        if config.mode == IdsVariantConfig.Mode.POD:
            return CONFIG_STATUS_POD if self.is_pod_ready(config) else CONFIG_STATUS_NEEDS_CONFIG
        return CONFIG_STATUS_NEEDS_CONFIG

    def is_pod_ready(self, config: IdsVariantConfig) -> bool:
        if not config.blank_variant_id:
            return False
        blank = config.blank_variant.blank
        required = blank.placement_capabilities.filter(is_required=True, is_active=True)
        recipe = getattr(config, "recipe", None)
        if recipe is None:
            return not required.exists()
        slots = {
            (slot.placement, slot.technique_id): slot
            for slot in recipe.slots.filter(is_enabled=True)
        }
        for capability in required:
            slot = slots.get((capability.placement, capability.technique_id))
            if slot is None or not slot.print_reference.strip():
                return False
        return True

    def drawer_context(self, *, actor, variant: ShopifyVariant) -> dict:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.variant_drawer",
            action="pod.variant_config.permission_rejected",
        )
        config = self.get_or_create_config(variant)
        if config.mode == IdsVariantConfig.Mode.POD and not hasattr(config, "recipe"):
            PodRecipe.objects.get_or_create(variant_config=config)
            config = IdsVariantConfig.objects.select_related(
                "blank_variant__blank",
                "recipe",
            ).prefetch_related(
                "recipe__slots__technique",
                "blank_variant__blank__placement_capabilities__technique",
            ).get(pk=config.pk)
        capabilities = []
        if config.blank_variant_id:
            capabilities = list(
                config.blank_variant.blank.placement_capabilities.filter(is_active=True)
            )
        slots_by_key = {}
        if hasattr(config, "recipe"):
            slots_by_key = {
                (slot.placement, slot.technique_id): slot for slot in config.recipe.slots.all()
            }
        slot_rows = []
        for capability in capabilities:
            slot = slots_by_key.get((capability.placement, capability.technique_id))
            slot_rows.append(
                {
                    "capability": capability,
                    "slot": slot,
                    "placement": capability.placement,
                    "placement_label": capability.get_placement_display(),
                    "technique": capability.technique,
                    "is_required": capability.is_required,
                    "is_enabled": slot.is_enabled if slot else capability.is_required,
                    "print_reference": slot.print_reference if slot else "",
                }
            )
        return {
            "variant": variant,
            "config": config,
            "status": self.configuration_status(config),
            "slot_rows": slot_rows,
            "modes": IdsVariantConfig.Mode.choices,
            "blank_variants": BlankVariant.objects.filter(is_active=True).select_related("blank"),
            "templates": PodRecipeTemplate.objects.filter(
                blank_id=config.blank_variant.blank_id if config.blank_variant_id else None
            )
            if config.blank_variant_id
            else PodRecipeTemplate.objects.none(),
        }

    def save_config(
        self,
        *,
        actor,
        variant_public_id,
        payload: VariantConfigPayload,
        source: str,
        merchant_actor=False,
    ) -> IdsVariantConfig:
        if merchant_actor:
            raise ValidationError("Surface marchand non activée dans ce lot.")
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.variant_config.permission_rejected",
        )
        try:
            with transaction.atomic():
                variant = ShopifyVariant.objects.select_for_update().get(
                    public_id=variant_public_id
                )
                config, _created = IdsVariantConfig.objects.get_or_create(variant=variant)
                config = IdsVariantConfig.objects.select_for_update().get(pk=config.pk)
                mode = payload.mode
                if mode not in IdsVariantConfig.Mode.values:
                    raise ValidationError("Mode variante invalide.")
                config.mode = mode
                config.staff_locked = payload.staff_locked
                config.blank_variant = None
                config.finished_sku = ""
                if mode == IdsVariantConfig.Mode.POD:
                    if not payload.blank_variant_public_id:
                        raise ValidationError("Blank support obligatoire en mode POD.")
                    blank_variant = BlankVariant.objects.filter(
                        public_id=payload.blank_variant_public_id,
                        is_active=True,
                    ).first()
                    if blank_variant is None:
                        raise ValidationError("Variante blank introuvable.")
                    config.blank_variant = blank_variant
                    self._save_pod_slots(
                        config=config,
                        slots=payload.slots,
                        source=source,
                        actor=actor,
                    )
                elif mode == IdsVariantConfig.Mode.ON_STOCK:
                    config.finished_sku = clean_sku(payload.finished_sku, field_label="SKU fini")
                    PodRecipe.objects.filter(variant_config=config).delete()
                else:
                    PodRecipe.objects.filter(variant_config=config).delete()
                config.save()
                record_event(
                    action="pod.variant_config.saved",
                    actor=actor,
                    target=config,
                    metadata={
                        "source": source,
                        "mode": config.mode,
                        "status": self.configuration_status(config),
                    },
                )
                return config
        except ValidationError as exc:
            record_event(
                action="pod.variant_config.save_rejected",
                actor=actor,
                status="failure",
                message=validation_message(exc),
                metadata={"source": source, "variant": str(variant_public_id)},
            )
            raise

    def apply_template(
        self,
        *,
        actor,
        variant_public_id,
        template_public_id,
        source: str,
    ) -> IdsVariantConfig:
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.variant_config.permission_rejected",
        )
        template = (
            PodRecipeTemplate.objects.prefetch_related("slots__technique")
            .filter(public_id=template_public_id)
            .first()
        )
        if template is None:
            raise ValidationError("Template introuvable.")
        blank_variant = BlankVariant.objects.filter(blank=template.blank, is_active=True).first()
        if blank_variant is None:
            raise ValidationError("Le template requiert au moins une variante blank active.")
        slots = tuple(
            VariantSlotPayload(
                placement=slot.placement,
                technique_public_id=str(slot.technique.public_id),
                is_enabled=True,
                print_reference=slot.print_reference,
                display_order=slot.display_order,
            )
            for slot in template.slots.all()
        )
        payload = VariantConfigPayload(
            mode=IdsVariantConfig.Mode.POD,
            blank_variant_public_id=str(blank_variant.public_id),
            slots=slots,
        )
        return self.save_config(
            actor=actor,
            variant_public_id=variant_public_id,
            payload=payload,
            source=source,
        )

    def _save_pod_slots(
        self,
        *,
        config: IdsVariantConfig,
        slots: tuple[VariantSlotPayload, ...],
        source: str,
        actor,
    ) -> None:
        blank = config.blank_variant.blank
        allowed = {
            (cap.placement, str(cap.technique.public_id)): cap
            for cap in blank.placement_capabilities.filter(is_active=True).select_related(
                "technique"
            )
        }
        recipe, _ = PodRecipe.objects.get_or_create(variant_config=config)
        recipe.slots.all().delete()
        seen_required = set()
        for index, slot_payload in enumerate(slots):
            capability = allowed.get((slot_payload.placement, slot_payload.technique_public_id))
            if capability is None:
                raise ValidationError("Pose / technique non autorisée sur ce blank.")
            if capability.is_required and not slot_payload.is_enabled:
                raise ValidationError("Une pose requise ne peut pas être désactivée.")
            if capability.is_required and not slot_payload.print_reference.strip():
                placement_label = capability.get_placement_display()
                raise ValidationError(
                    f"Fichier HD manquant pour la pose requise {placement_label}."
                )
            if not capability.is_required and not slot_payload.is_enabled:
                continue
            technique = PrintTechnique.objects.get(public_id=slot_payload.technique_public_id)
            PodRecipeSlot.objects.create(
                recipe=recipe,
                placement=slot_payload.placement,
                technique=technique,
                is_enabled=True,
                print_reference=slot_payload.print_reference.strip(),
                display_order=slot_payload.display_order or index,
            )
            if capability.is_required:
                seen_required.add((capability.placement, capability.technique_id))
        for capability in blank.placement_capabilities.filter(is_required=True, is_active=True):
            if (capability.placement, capability.technique_id) not in seen_required:
                raise ValidationError(
                    "Toutes les poses requises du blank doivent être configurées."
                )
