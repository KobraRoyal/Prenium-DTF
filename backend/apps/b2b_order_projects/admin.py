from django.contrib import admin

from .models import B2BOrderProject, B2BOrderProjectItem


class B2BOrderProjectItemInline(admin.TabularInline):
    model = B2BOrderProjectItem
    extra = 0
    readonly_fields = ("public_id", "created_at", "updated_at")


@admin.register(B2BOrderProject)
class B2BOrderProjectAdmin(admin.ModelAdmin):
    list_display = ("project_number", "name", "customer", "status", "updated_at")
    list_filter = ("status", "order_mode")
    search_fields = ("project_number", "name", "customer__name")
    readonly_fields = ("public_id", "project_number", "created_at", "updated_at")
    inlines = (B2BOrderProjectItemInline,)
