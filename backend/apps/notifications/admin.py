from django.contrib import admin

from apps.notifications.models import EmailTemplate


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
