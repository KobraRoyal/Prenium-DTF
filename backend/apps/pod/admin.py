from django.contrib import admin

from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    BlankVariant,
    IdsVariantConfig,
    MarkingZone,
    PodRecipeTemplate,
    PodRipLot,
    PodUnit,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
    ShopifyWebhookReceipt,
)


class ProtectedReferenceAdminMixin:
    """Reference lifecycle is managed by audited application services."""

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PrintTechnique)
class PrintTechniqueAdmin(ProtectedReferenceAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "rip_directory", "is_active", "public_id")
    search_fields = ("code", "name")
    readonly_fields = (
        "public_id",
        "code",
        "name",
        "rip_directory",
        "export_extension",
        "display_order",
        "is_active",
    )


class BlankVariantInline(admin.TabularInline):
    model = BlankVariant
    extra = 0
    readonly_fields = (
        "public_id",
        "sku",
        "size_label",
        "color_name",
        "color_hex",
        "is_active",
        "photo",
        "photo_thumb",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class BlankPlacementInline(admin.TabularInline):
    model = BlankPlacementCapability
    extra = 0
    readonly_fields = (
        "public_id",
        "placement",
        "technique",
        "is_required",
        "is_active",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Blank)
class BlankAdmin(ProtectedReferenceAdminMixin, admin.ModelAdmin):
    list_display = ("sku", "name", "brand", "is_active", "public_id")
    search_fields = ("sku", "name")
    readonly_fields = (
        "public_id",
        "sku",
        "name",
        "brand",
        "is_active",
        "photo",
        "photo_thumb",
        "allowed_zones",
        "allowed_techniques",
        "marking_options_configured",
    )
    inlines = (BlankVariantInline, BlankPlacementInline)


@admin.register(MarkingZone)
class MarkingZoneAdmin(ProtectedReferenceAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "public_id")
    readonly_fields = ("public_id", "code", "name", "display_order", "is_active")


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    list_display = ("name", "shop_domain", "slug", "is_active", "token_suffix", "connected_at")
    readonly_fields = (
        "public_id",
        "is_active",
        "token_suffix",
        "oauth_scopes",
        "connected_at",
    )
    fields = (
        "name",
        "slug",
        "shop_domain",
        "is_active",
        "token_suffix",
        "oauth_scopes",
        "connected_at",
        "public_id",
    )


@admin.register(ShopifyWebhookReceipt)
class ShopifyWebhookReceiptAdmin(admin.ModelAdmin):
    list_display = ("webhook_id", "shop_domain", "topic", "created_at")
    readonly_fields = ("public_id", "webhook_id", "shop_domain", "topic")
    search_fields = ("webhook_id", "shop_domain")


@admin.register(ShopifyProduct)
class ShopifyProductAdmin(admin.ModelAdmin):
    list_display = ("title", "store", "external_id", "public_id")
    search_fields = ("title", "external_id")
    readonly_fields = ("public_id",)


@admin.register(ShopifyVariant)
class ShopifyVariantAdmin(admin.ModelAdmin):
    list_display = ("title", "sku", "product", "public_id")
    search_fields = ("title", "sku")
    readonly_fields = ("public_id",)


@admin.register(IdsVariantConfig)
class IdsVariantConfigAdmin(admin.ModelAdmin):
    list_display = ("variant", "mode", "blank_variant", "finished_sku", "staff_locked")
    readonly_fields = ("public_id",)


@admin.register(PodRecipeTemplate)
class PodRecipeTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "blank", "store")
    readonly_fields = ("public_id",)


@admin.register(PodRipLot)
class PodRipLotAdmin(admin.ModelAdmin):
    list_display = ("code", "technique", "status", "file_count", "public_id")
    readonly_fields = ("public_id",)


@admin.register(PodUnit)
class PodUnitAdmin(admin.ModelAdmin):
    list_display = ("scan_identifier", "status", "lot", "variant")
    search_fields = ("scan_identifier",)
    readonly_fields = ("public_id",)
