from django.contrib import admin

from .models import SendcloudWebhookEvent, Shipment, ShippingMethod


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "base_price",
        "currency",
        "is_pickup",
        "is_active",
        "display_order",
    )
    list_filter = ("is_active", "is_pickup")
    search_fields = ("code", "name")
    ordering = ("display_order", "name")
    prepopulated_fields = {"code": ("name",)}


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "status",
        "shipping_option_code",
        "tracking_number",
        "sendcloud_status_code",
        "created_by",
        "updated_by",
        "updated_at",
    )
    list_filter = ("status", "shipping_option_code", "sendcloud_status_code", "updated_at")
    search_fields = (
        "order__public_id",
        "order__customer__name",
        "tracking_number",
        "sendcloud_shipment_id",
        "sendcloud_parcel_id",
    )
    readonly_fields = (
        "public_id",
        "order",
        "created_by",
        "updated_by",
        "status",
        "shipping_option_code",
        "contract_id",
        "tracking_number",
        "tracking_url",
        "sendcloud_shipment_id",
        "sendcloud_parcel_id",
        "sendcloud_status_code",
        "sendcloud_status_message",
        "label_file",
        "label_filename",
        "label_mime_type",
        "label_retrieved_at",
        "last_api_sync_at",
        "last_error_message",
        "source",
        "request_snapshot",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order", "created_by", "updated_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(SendcloudWebhookEvent)
class SendcloudWebhookEventAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "customer",
        "shipment",
        "provider_event_id",
        "processed_at",
        "created_at",
    )
    list_filter = ("processed_at", "created_at")
    search_fields = (
        "customer__name",
        "customer__public_id",
        "shipment__public_id",
        "provider_event_id",
        "payload_hash",
    )
    readonly_fields = (
        "public_id",
        "customer",
        "shipment",
        "event_key",
        "provider_event_id",
        "payload_hash",
        "processed_at",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("customer", "shipment")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
