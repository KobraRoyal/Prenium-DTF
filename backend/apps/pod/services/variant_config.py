from __future__ import annotations

import secrets
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from apps.auditlog.services import record_event
from apps.pod.models import (
    Blank,
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
from apps.pod.services.blank_marking_options import capabilities_for_blank
from apps.pod.services.drive_hd_sources import DriveHdSourceService
from apps.pod.services.rip_source import RipSourceService
from apps.pod.services.validation import clean_sku, require_staff_perm, validation_message
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from apps.uploads.models import AssetVersion

CONFIG_STATUS_UNMANAGED = "unmanaged"
CONFIG_STATUS_DISABLED = "disabled"
CONFIG_STATUS_VIRTUAL = "virtual"
CONFIG_STATUS_ON_STOCK = "on_stock"
CONFIG_STATUS_POD = "pod"
CONFIG_STATUS_NEEDS_CONFIG = "needs_config"


def _generate_demo_webhook_secret() -> str:
    return secrets.token_urlsafe(48)


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
                "ids_config__blank_variant__blank__allowed_zones",
                "ids_config__blank_variant__blank__allowed_techniques",
            )
            .filter(public_id=variant_public_id)
            .first()
        )
        if variant is None:
            raise ValidationError("Variante Shopify introuvable.")
        return variant

    @transaction.atomic
    def ensure_demo_catalog(self, *, actor) -> ShopifyProduct:
        """Create demo-only catalog data from an explicit seed/bootstrap call."""
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
                "webhook_secret": _generate_demo_webhook_secret,
            },
        )
        if not store.webhook_secret:
            store.webhook_secret = _generate_demo_webhook_secret()
            store.save(update_fields=["webhook_secret", "updated_at"])
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
    rip_source = RipSourceService()
    drive_hd_source = DriveHdSourceService()

    def get_config(self, variant: ShopifyVariant) -> IdsVariantConfig | None:
        return IdsVariantConfig.objects.filter(variant=variant).first()

    def get_or_create_config(self, variant: ShopifyVariant) -> IdsVariantConfig:
        config, _created = IdsVariantConfig.objects.get_or_create(variant=variant)
        return config

    def configuration_status(self, config: IdsVariantConfig | None) -> str:
        if config is None:
            return CONFIG_STATUS_UNMANAGED
        if config.mode == IdsVariantConfig.Mode.UNMANAGED:
            return CONFIG_STATUS_UNMANAGED
        if config.mode == IdsVariantConfig.Mode.DISABLED:
            return CONFIG_STATUS_DISABLED
        if config.mode == IdsVariantConfig.Mode.VIRTUAL:
            return CONFIG_STATUS_VIRTUAL
        if config.mode == IdsVariantConfig.Mode.ON_STOCK:
            return CONFIG_STATUS_ON_STOCK if config.finished_sku else CONFIG_STATUS_NEEDS_CONFIG
        if config.mode == IdsVariantConfig.Mode.POD:
            return CONFIG_STATUS_POD if self.is_pod_ready(config) else CONFIG_STATUS_NEEDS_CONFIG
        return CONFIG_STATUS_NEEDS_CONFIG

    def is_pod_ready(self, config: IdsVariantConfig) -> bool:
        store = config.variant.product.store
        if not config.blank_variant_id or not store.customer_id:
            return False
        blank = config.blank_variant.blank
        if not config.blank_variant.is_active or not blank.is_active:
            return False
        capabilities = capabilities_for_blank(blank)
        required = [capability for capability in capabilities if capability.is_required]
        active_capability_keys = {
            (capability.placement, capability.technique_id) for capability in capabilities
        }
        recipe = getattr(config, "recipe", None)
        if recipe is None:
            return False
        enabled_slots = getattr(recipe, "pod_ready_enabled_slots", None)
        if enabled_slots is None:
            enabled_slots = recipe.slots.filter(is_enabled=True).select_related(
                "technique", "source_asset_version__asset", "source_drive_hd__asset_version"
            )
        slots = {(slot.placement, slot.technique_id): slot for slot in enabled_slots}
        if not slots:
            return False
        for capability in required:
            if (capability.placement, capability.technique_id) not in slots:
                return False
        for slot in slots.values():
            if not slot.technique.is_active:
                return False
            if (slot.placement, slot.technique_id) not in active_capability_keys:
                return False
            drive_source = getattr(slot, "source_drive_hd", None)
            if drive_source is not None and (
                drive_source.customer_id != store.customer_id
                or drive_source.status != drive_source.Status.READY
                or drive_source.asset_version_id != slot.source_asset_version_id
            ):
                return False
            try:
                self.rip_source.resolve(slot=slot, store=store, technique=slot.technique)
            except ValidationError:
                return False
        return True

    def drawer_context(
        self,
        *,
        actor,
        variant: ShopifyVariant,
        preview_blank_public_id: str = "",
        refresh_drive: bool = False,
    ) -> dict:
        require_staff_perm(
            actor,
            self.view_permission,
            source="pod.variant_drawer",
            action="pod.variant_config.permission_rejected",
        )
        config = self.get_config(variant) or IdsVariantConfig(variant=variant)
        original_blank_id = config.blank_variant_id
        preview_blank = None
        if preview_blank_public_id:
            preview_blank = (
                BlankVariant.objects.filter(
                    public_id=preview_blank_public_id,
                    is_active=True,
                    blank__is_active=True,
                )
                .select_related("blank")
                .first()
            )
            if preview_blank is None:
                raise ValidationError("Variante blank introuvable.")
            config.blank_variant = preview_blank
            config.mode = IdsVariantConfig.Mode.POD
        capabilities = []
        if config.blank_variant_id:
            capabilities = capabilities_for_blank(config.blank_variant.blank)
        slots_by_key = {}
        if original_blank_id == config.blank_variant_id and hasattr(config, "recipe"):
            slots_by_key = {
                (slot.placement, slot.technique_id): slot for slot in config.recipe.slots.all()
            }
        store = variant.product.store
        drive_result = self.drive_hd_source.list_options(actor=actor, refresh=refresh_drive)
        candidates = (
            list(
                AssetVersion.objects.for_customer(store.customer)
                .filter(
                    analysis_status=AssetVersion.AnalysisStatus.READY,
                    asset__is_archived=False,
                )
                .select_related("asset")
            )
            if store.customer_id
            else []
        )
        slot_rows = []
        for capability in capabilities:
            slot = slots_by_key.get((capability.placement, capability.technique_id))
            safe_slot = slot
            if slot and (
                (slot.source_drive_hd_id and slot.source_drive_hd.customer_id != store.customer_id)
                or (
                    slot.source_asset_version_id
                    and slot.source_asset_version.customer_id != store.customer_id
                )
            ):
                safe_slot = None
            slot_rows.append(
                {
                    "capability": capability,
                    "slot": slot,
                    "placement": capability.placement,
                    "placement_label": capability.get_placement_display(),
                    "technique": capability.technique,
                    "is_required": capability.is_required,
                    "is_enabled": slot.is_enabled if slot else capability.is_required,
                    "print_reference": safe_slot.print_reference if safe_slot else "",
                    "source_asset_version_public_id": (
                        str(safe_slot.source_asset_version.public_id)
                        if safe_slot and safe_slot.source_asset_version_id
                        else ""
                    ),
                    "source_drive_file_id": (
                        safe_slot.source_drive_hd.drive_file_id
                        if safe_slot and safe_slot.source_drive_hd_id
                        else ""
                    ),
                    "drive_source_error": (
                        safe_slot.source_drive_hd.last_error
                        if safe_slot and safe_slot.source_drive_hd_id
                        else ""
                    ),
                    "drive_source_status": (
                        safe_slot.source_drive_hd.status
                        if safe_slot and safe_slot.source_drive_hd_id
                        else ""
                    ),
                    "drive_options": (
                        [
                            option
                            for option in drive_result.options
                            if capability.technique.code == "dtf"
                            or Path(option.name).suffix.lower() == ".png"
                        ]
                        if capability.technique.export_extension.strip().lower() in {"png", ".png"}
                        else []
                    ),
                    "asset_options": [
                        version
                        for version in candidates
                        if self._source_compatible(
                            version=version,
                            store=store,
                            technique=capability.technique,
                        )
                    ],
                }
            )
        return {
            "variant": variant,
            "config": config,
            "status": (
                CONFIG_STATUS_NEEDS_CONFIG
                if preview_blank is not None
                else self.configuration_status(config)
            ),
            "slot_rows": slot_rows,
            "modes": IdsVariantConfig.Mode.choices,
            "blank_variants": BlankVariant.objects.filter(
                is_active=True,
                blank__is_active=True,
            ).select_related("blank"),
            "store_customer": store.customer,
            "drive_options": drive_result.options,
            "drive_source_configured": drive_result.configured,
            "drive_source_error": drive_result.error,
            "drive_empty_file_count": drive_result.empty_file_count,
            "drive_source_folder_url": (
                "https://drive.google.com/drive/folders/"
                + str(getattr(settings, "GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID", ""))
                if drive_result.configured and actor.has_perm(self.manage_permission)
                else ""
            ),
            "templates": PodRecipeTemplate.objects.filter(
                Q(store__isnull=True) | Q(store=store),
                blank_id=config.blank_variant.blank_id if config.blank_variant_id else None,
            )
            if config.blank_variant_id
            else PodRecipeTemplate.objects.none(),
        }

    def mapping_choices(self, context, *, placement="", technique_id="", action="", slot_key=""):
        """Build the editable mapping from the selected child's parent capabilities."""
        rows = context["slot_rows"]
        keys = {f"{row['placement']}:{row['technique'].public_id}": row for row in rows}
        if action:
            if context["config"].mode != IdsVariantConfig.Mode.POD:
                raise ValidationError("Sélectionnez un support POD avant d’ajouter un marquage.")
            key = f"{placement}:{technique_id}" if action == "add_slot" else slot_key
            row = keys.get(key)
            if row is None:
                raise ValidationError("Zone / technique non autorisée sur le support sélectionné.")
            if action == "remove_slot" and row["is_required"]:
                raise ValidationError(
                    "Ce marquage est requis par le support et ne peut pas être retiré."
                )
            if action == "add_slot" and row["is_enabled"]:
                raise ValidationError("Ce marquage est déjà ajouté.")
            row["is_enabled"] = action == "add_slot"
        for key, row in keys.items():
            row["mapping_key"] = key
        available = [row for row in rows if not row["is_enabled"] and not row["is_required"]]
        zones = dict((row["placement"], row["placement_label"]) for row in available)
        selected_zone = placement if placement in zones else next(iter(zones), "")
        technique_options = [
            row["technique"] for row in available if row["placement"] == selected_zone
        ]
        allowed_techniques = {str(technique.public_id) for technique in technique_options}
        selected_technique = (
            technique_id
            if technique_id in allowed_techniques
            else (str(technique_options[0].public_id) if technique_options else "")
        )
        context.update(
            mapping_rows=[row for row in rows if row["is_enabled"] or row["is_required"]],
            mapping_zones=list(zones.items()),
            mapping_techniques=technique_options,
            mapping_placement=selected_zone,
            mapping_technique=selected_technique,
        )
        return context

    def _source_compatible(self, *, version: AssetVersion, store, technique) -> bool:
        try:
            self.rip_source.validate_version(version=version, store=store, technique=technique)
        except ValidationError:
            return False
        return True

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
            message = (
                "Écriture marchand désactivée : authentification et périmètre Customer requis."
            )
            record_event(
                action="pod.variant_config.save_rejected",
                status="failure",
                message=message,
                metadata={"source": source, "variant": str(variant_public_id)},
            )
            raise ValidationError(message)
        else:
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
                        blank__is_active=True,
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
        variant = (
            ShopifyVariant.objects.select_related("product__store")
            .filter(public_id=variant_public_id)
            .first()
        )
        if variant is None:
            raise ValidationError("Variante Shopify introuvable.")
        template = (
            PodRecipeTemplate.objects.prefetch_related("slots__technique")
            .filter(
                Q(store__isnull=True) | Q(store=variant.product.store),
                public_id=template_public_id,
            )
            .first()
        )
        if template is None:
            raise ValidationError("Template introuvable.")
        blank_variant = BlankVariant.objects.filter(
            blank=template.blank,
            blank__is_active=True,
            is_active=True,
        ).first()
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
        blank = Blank.objects.select_for_update().get(pk=config.blank_variant.blank_id)
        if not blank.is_active:
            raise ValidationError("Le support vierge est inactif.")
        capabilities = capabilities_for_blank(blank)
        allowed = {(cap.placement, str(cap.technique.public_id)): cap for cap in capabilities}
        recipe, _ = PodRecipe.objects.get_or_create(variant_config=config)
        recipe.slots.all().delete()
        seen_required = set()
        for index, slot_payload in enumerate(slots):
            capability = allowed.get((slot_payload.placement, slot_payload.technique_public_id))
            if capability is None:
                raise ValidationError("Pose / technique non autorisée sur ce blank.")
            if capability.is_required and not slot_payload.is_enabled:
                raise ValidationError("Une pose requise ne peut pas être désactivée.")
            if not capability.is_required and not slot_payload.is_enabled:
                continue
            technique = PrintTechnique.objects.filter(
                public_id=slot_payload.technique_public_id,
                is_active=True,
            ).first()
            if technique is None:
                raise ValidationError("Technique inactive ou introuvable.")
            version = None
            drive_source = None
            if slot_payload.source_asset_version_public_id and slot_payload.source_drive_file_id:
                raise ValidationError("Choisissez une source HD locale ou Drive, pas les deux.")
            if slot_payload.source_asset_version_public_id:
                version = (
                    AssetVersion.objects.select_related("asset")
                    .filter(public_id=slot_payload.source_asset_version_public_id)
                    .first()
                )
                if version is None:
                    raise ValidationError("Version du fichier HD introuvable.")
                self.rip_source.validate_version(
                    version=version,
                    store=config.variant.product.store,
                    technique=technique,
                )
            elif slot_payload.source_drive_file_id:
                store = config.variant.product.store
                drive_source = self.drive_hd_source.select(
                    customer=store.customer,
                    drive_file_id=slot_payload.source_drive_file_id,
                    actor=actor,
                    source=source,
                )
                if (
                    technique.code != "dtf"
                    and Path(drive_source.original_filename).suffix.lower() != ".png"
                ):
                    raise ValidationError("Cette technique n'accepte que les fichiers HD PNG.")
                if (
                    drive_source.status == drive_source.Status.READY
                    and drive_source.asset_version_id
                ):
                    version = drive_source.asset_version
                    self.rip_source.validate_version(
                        version=version,
                        store=store,
                        technique=technique,
                        drive_source=drive_source,
                    )
            PodRecipeSlot.objects.create(
                recipe=recipe,
                placement=slot_payload.placement,
                technique=technique,
                is_enabled=True,
                print_reference=(
                    version.original_filename[:255]
                    if version is not None
                    else slot_payload.print_reference.strip()
                ),
                source_asset_version=version,
                source_drive_hd=drive_source,
                display_order=slot_payload.display_order or index,
            )
            if drive_source is not None and drive_source.status != drive_source.Status.READY:
                from apps.pod.tasks import import_pod_drive_hd_source_task

                transaction.on_commit(
                    lambda source_public_id=str(drive_source.public_id), selected=drive_source: (
                        self._enqueue_drive_import(
                            task=import_pod_drive_hd_source_task,
                            source_public_id=source_public_id,
                            drive_source=selected,
                            actor=actor,
                            source=source,
                        )
                    ),
                    robust=True,
                )
            if capability.is_required:
                seen_required.add((capability.placement, capability.technique_id))
        for capability in (cap for cap in capabilities if cap.is_required):
            if (capability.placement, capability.technique_id) not in seen_required:
                raise ValidationError(
                    "Toutes les poses requises du blank doivent être configurées."
                )

    @staticmethod
    def _enqueue_drive_import(
        *, task, source_public_id: str, drive_source, actor, source: str
    ) -> None:
        try:
            task.delay(source_public_id)
        except Exception as exc:
            record_event(
                action="pod.drive_hd_source.dispatch_failed",
                actor=actor,
                target=drive_source,
                status="failure",
                message="La source Drive HD reste en attente d'import.",
                metadata={"source": source, "error_type": type(exc).__name__},
            )
