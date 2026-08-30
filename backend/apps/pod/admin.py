from django.contrib import admin

from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    BlankVariant,
    IdsVariantConfig,
    PodRecipeTemplate,
    PodRipLot,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)


@admin.register(PrintTechnique)
class PrintTechniqueAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "rip_directory", "is_active", "public_id")
    search_fields = ("code", "name")
    readonly_fields = ("public_id",)


class BlankVariantInline(admin.TabularInline):
    model = BlankVariant
    extra = 0
    readonly_fields = ("public_id",)


class BlankPlacementInline(admin.TabularInline):
    model = BlankPlacementCapability
    extra = 0
    readonly_fields = ("public_id",)


@admin.register(Blank)
class BlankAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "brand", "is_active", "public_id")
    search_fields = ("sku", "name")
    readonly_fields = ("public_id",)
    inlines = (BlankVariantInline, BlankPlacementInline)


@admin.register(ShopifyStore)
class ShopifyStoreAdmin(admin.ModelAdmin):
    list_display = ("name", "shop_domain", "slug", "is_active")
    readonly_fields = ("public_id",)


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
