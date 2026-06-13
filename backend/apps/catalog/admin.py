from django.contrib import admin

from .models import CatalogService


@admin.register(CatalogService)
class CatalogServiceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "service_type",
        "unit",
        "base_price",
        "currency",
        "is_active",
    )
    list_filter = ("service_type", "unit", "is_active")
    search_fields = ("name", "code", "description")
    readonly_fields = ("public_id", "created_at", "updated_at")
    ordering = ("display_order", "name")
