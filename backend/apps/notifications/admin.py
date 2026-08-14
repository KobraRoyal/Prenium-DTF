from django.contrib import admin

from apps.notifications.models import EmailTemplate, VolumeDiscountTierNotification


@admin.register(EmailTemplate)
class EmailTemplateAdmin(admin.ModelAdmin):
    list_display = ("event", "audience", "is_active", "version", "updated_by", "updated_at")
    list_filter = ("event", "audience", "is_active")
    search_fields = ("subject_template", "body_template", "updated_by__email")
    readonly_fields = ("public_id", "version", "updated_by", "created_at", "updated_at")

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(VolumeDiscountTierNotification)
class VolumeDiscountTierNotificationAdmin(admin.ModelAdmin):
    list_display = (
        "customer",
        "month",
        "threshold_linear_m",
        "discount_percent",
        "status",
        "attempt_count",
        "delivery_started_at",
        "sent_at",
    )
    list_filter = ("status", "month")
    search_fields = ("customer__name", "customer__billing_email")
    readonly_fields = (
        "public_id",
        "customer",
        "month",
        "threshold_linear_m",
        "monthly_volume_linear_m",
        "discount_percent",
        "discount_amount",
        "status",
        "attempt_count",
        "delivery_started_at",
        "sent_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
