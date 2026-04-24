from django.contrib import admin

from .models import ProspectProfile


@admin.register(ProspectProfile)
class ProspectProfileAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "company",
        "status",
        "service_interest",
        "created_at",
    )
    list_filter = ("status", "activity_type", "source")
    search_fields = ("email", "company", "first_name", "last_name")
    readonly_fields = ("public_id", "created_at", "updated_at")
    raw_id_fields = ("user", "customer")
