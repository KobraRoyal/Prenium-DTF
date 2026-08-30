from django.contrib import admin

from apps.pod.models import Blank, BlankPlacementCapability, BlankVariant, PrintTechnique


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
