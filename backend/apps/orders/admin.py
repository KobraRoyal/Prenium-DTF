from django.contrib import admin

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    fields = (
        "position",
        "service",
        "service_name",
        "quantity",
        "unit_price",
        "line_total",
        "public_id",
    )
    readonly_fields = ("service_name", "quantity", "unit_price", "line_total", "public_id")
    autocomplete_fields = ("service",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "customer",
        "status",
        "billing_mode",
        "pricing_status",
        "total_amount",
        "currency",
        "created_at",
    )
    list_filter = ("status", "currency", "source", "billing_mode", "pricing_status")
    search_fields = ("customer__name", "customer__billing_email")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("customer", "created_by", "billing_statement")
    inlines = (OrderLineInline,)


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin):
    list_display = ("order", "position", "service_name", "quantity", "line_total")
    readonly_fields = ("public_id", "created_at", "updated_at")
    autocomplete_fields = ("order", "service")
