from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.auditlog.admin import AdminAuditMixin

from .forms import UserChangeForm, UserCreationForm
from .models import User


@admin.register(User)
class UserAdmin(AdminAuditMixin, DjangoUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    ordering = ("email",)
    audit_create_action = "admin.user.created"
    audit_update_action = "admin.user.updated"
    audit_delete_action = "admin.user.deleted"
    audit_fields = (
        "email",
        "is_active",
        "is_staff",
        "is_superuser",
        "staff_mfa_required",
        "staff_mfa_enabled",
        "groups",
        "user_permissions",
    )
    list_display = (
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "staff_mfa_required",
        "staff_mfa_enabled",
        "is_superuser",
        "is_active",
    )
    list_filter = (
        "is_staff",
        "staff_mfa_required",
        "staff_mfa_enabled",
        "is_superuser",
        "is_active",
    )
    search_fields = ("email", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name")}),
        ("Security", {"fields": ("staff_mfa_required", "staff_mfa_enabled")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
        ("Public identifiers", {"fields": ("public_id",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "first_name", "last_name", "password1", "password2"),
            },
        ),
    )
    readonly_fields = ("public_id", "last_login", "date_joined")
