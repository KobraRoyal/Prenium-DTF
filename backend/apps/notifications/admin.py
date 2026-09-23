from django.contrib import admin

from apps.notifications.models import (
    EmailTemplate,
    PushDelivery,
    StaffPushSubscription,
    VolumeDiscountTierNotification,
    WorkshopNotificationEvent,
)


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


class _ReadOnlyNotificationAdmin(admin.ModelAdmin):
    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(StaffPushSubscription)
class StaffPushSubscriptionAdmin(_ReadOnlyNotificationAdmin):
    list_display = (
        "public_id",
        "staff_membership",
        "is_active",
        "last_seen_at",
        "consecutive_failures",
        "last_failure_code",
    )
    list_filter = ("is_active", "last_failure_code")
    readonly_fields = (
        "public_id",
        "staff_membership",
        "endpoint_digest",
        "is_active",
        "last_seen_at",
        "disabled_at",
        "expires_at",
        "consecutive_failures",
        "last_failure_code",
        "created_at",
        "updated_at",
    )
    exclude = ("endpoint_ciphertext", "p256dh_ciphertext", "auth_ciphertext")


@admin.register(WorkshopNotificationEvent)
class WorkshopNotificationEventAdmin(_ReadOnlyNotificationAdmin):
    list_display = ("public_id", "event_type", "customer", "order", "source", "created_at")
    list_filter = ("event_type", "source")
    search_fields = ("public_id", "customer__public_id", "order__public_id")
    readonly_fields = (
        "public_id",
        "event_type",
        "customer",
        "order",
        "actor",
        "source",
        "created_at",
        "updated_at",
    )


@admin.register(PushDelivery)
class PushDeliveryAdmin(_ReadOnlyNotificationAdmin):
    list_display = (
        "public_id",
        "event",
        "subscription",
        "status",
        "attempt_count",
        "claimed_at",
        "delivered_at",
    )
    list_filter = ("status", "failure_code")
    search_fields = ("public_id", "event__public_id", "subscription__public_id")
    readonly_fields = (
        "public_id",
        "event",
        "subscription",
        "status",
        "attempt_count",
        "claimed_at",
        "next_attempt_at",
        "delivered_at",
        "failure_code",
        "created_at",
        "updated_at",
    )
