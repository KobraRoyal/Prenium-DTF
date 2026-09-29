from __future__ import annotations

from django.db.models import Count, Prefetch, Q

from apps.inventory.models import StorageLocation
from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    PodRecipeSlot,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.variant_config import (
    CONFIG_STATUS_NEEDS_CONFIG,
    CONFIG_STATUS_UNMANAGED,
    VariantConfigService,
)


class PodSettingsOverviewService:
    """Build the read-only aggregate shown on the POD settings landing page."""

    variant_config_service = VariantConfigService()

    def build(self, *, actor) -> dict[str, int]:
        overview = {
            "disconnected_shops_count": 0,
            "variants_needing_mapping_count": 0,
            "supports_without_variants_count": 0,
            "locations_count": 0,
        }
        if actor.has_perm("pod.manage_pod_catalog"):
            overview.update(self._catalog_overview())
        if actor.has_perm("inventory.manage_warehouse"):
            overview["locations_count"] = StorageLocation.objects.filter(
                is_active=True,
                zone__is_active=True,
                zone__warehouse__is_active=True,
            ).count()
        return overview

    def _catalog_overview(self) -> dict[str, int]:
        variants = ShopifyVariant.objects.select_related(
            "product__store",
            "ids_config__blank_variant__blank",
            "ids_config__recipe",
        ).prefetch_related(
            Prefetch(
                "ids_config__blank_variant__blank__placement_capabilities",
                queryset=BlankPlacementCapability.objects.filter(
                    is_required=True,
                    is_active=True,
                ),
                to_attr="pod_ready_required_capabilities",
            ),
            Prefetch(
                "ids_config__recipe__slots",
                queryset=PodRecipeSlot.objects.filter(is_enabled=True).select_related(
                    "technique",
                    "source_asset_version__asset",
                ),
                to_attr="pod_ready_enabled_slots",
            ),
        )
        variants_needing_mapping_count = 0
        for variant in variants:
            config = getattr(variant, "ids_config", None)
            status = self.variant_config_service.configuration_status(config)
            if status in {CONFIG_STATUS_UNMANAGED, CONFIG_STATUS_NEEDS_CONFIG}:
                variants_needing_mapping_count += 1

        return {
            "disconnected_shops_count": ShopifyStore.objects.filter(
                is_active=True, access_token_encrypted=""
            ).count(),
            "variants_needing_mapping_count": variants_needing_mapping_count,
            "supports_without_variants_count": Blank.objects.active()
            .annotate(
                active_variants_count=Count(
                    "variants",
                    filter=Q(variants__is_active=True),
                )
            )
            .filter(active_variants_count=0)
            .count(),
        }
