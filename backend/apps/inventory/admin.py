from django.contrib import admin

from apps.inventory.models import (
    ProductLocationRule,
    StockBalance,
    StorageLocation,
    Warehouse,
    WarehouseZone,
)


class WarehouseZoneInline(admin.TabularInline):
    model = WarehouseZone
    extra = 0
    readonly_fields = ("public_id",)


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "public_id")
    readonly_fields = ("public_id",)
    inlines = (WarehouseZoneInline,)


@admin.register(StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = ("code", "zone", "is_active", "public_id")
    search_fields = ("code",)
    readonly_fields = ("public_id",)
    autocomplete_fields = ("zone",)


@admin.register(WarehouseZone)
class WarehouseZoneAdmin(admin.ModelAdmin):
    list_display = ("code", "warehouse", "kind", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("public_id",)


@admin.register(ProductLocationRule)
class ProductLocationRuleAdmin(admin.ModelAdmin):
    list_display = ("sku_kind", "blank_variant", "finished_sku", "location", "owner_kind")
    readonly_fields = ("public_id",)


@admin.register(StockBalance)
class StockBalanceAdmin(admin.ModelAdmin):
    list_display = (
        "sku_kind",
        "blank_variant",
        "finished_sku",
        "location",
        "owner_kind",
        "qty_on_hand",
        "qty_reserved",
    )
    readonly_fields = ("public_id",)
