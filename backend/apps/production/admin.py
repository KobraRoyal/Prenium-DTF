from django.contrib import admin

from .models import ProductionJob, ProductionJobScanLog, ProductionJobTransition


class ProductionJobTransitionInline(admin.TabularInline):
    model = ProductionJobTransition
    extra = 0
    readonly_fields = (
        "from_status",
        "to_status",
        "reason",
        "source",
        "changed_by",
        "public_id",
        "created_at",
    )
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ProductionJob)
class ProductionJobAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "manufacturing_order_number",
        "scan_identifier",
        "status",
        "started_at",
        "completed_at",
        "last_transition_by",
        "last_transition_at",
    )
    list_filter = ("status", "last_transition_at", "completed_at")
    search_fields = (
        "order__public_id",
        "order__customer__name",
        "manufacturing_order_number",
        "scan_identifier",
    )
    readonly_fields = (
        "public_id",
        "order",
        "manufacturing_order_number",
        "scan_identifier",
        "status",
        "started_at",
        "completed_at",
        "last_transition_by",
        "last_transition_note",
        "last_transition_at",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order", "last_transition_by")
    inlines = (ProductionJobTransitionInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProductionJobTransition)
class ProductionJobTransitionAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "production_job",
        "from_status",
        "to_status",
        "changed_by",
        "source",
        "created_at",
    )
    list_filter = ("to_status", "source", "created_at")
    search_fields = (
        "production_job__order__public_id",
        "production_job__order__customer__name",
        "reason",
    )
    readonly_fields = (
        "public_id",
        "production_job",
        "changed_by",
        "from_status",
        "to_status",
        "reason",
        "source",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("production_job", "changed_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ProductionJobScanLog)
class ProductionJobScanLogAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "scan_identifier",
        "action",
        "outcome",
        "requested_status",
        "production_job",
        "actor",
        "source",
        "created_at",
    )
    list_filter = ("action", "outcome", "source", "created_at")
    search_fields = (
        "scan_identifier",
        "production_job__order__public_id",
        "production_job__order__customer__name",
        "message",
    )
    readonly_fields = (
        "public_id",
        "production_job",
        "actor",
        "scan_identifier",
        "action",
        "outcome",
        "requested_status",
        "source",
        "message",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("production_job", "actor")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
