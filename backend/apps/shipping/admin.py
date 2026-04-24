from django.contrib import admin

from .models import Shipment


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
