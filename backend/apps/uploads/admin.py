from django.contrib import admin

from .models import (
    Asset,
    AssetAnalysis,
    AssetVersion,
    OrderDriveFolder,
    OrderUpload,
    OrderUploadDriveSync,
    OrderUploadInspection,
)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ("public_id", "customer", "name", "current_version", "is_archived", "updated_at")
    list_filter = ("is_archived", "updated_at")
    search_fields = ("name", "customer__name", "public_id")
    readonly_fields = (
        "public_id",
        "customer",
        "created_by",
        "current_version",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AssetVersion)
class AssetVersionAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "asset",
        "version_number",
        "analysis_status",
        "mime_type",
        "size_bytes",
        "created_at",
    )
    list_filter = ("analysis_status", "mime_type", "created_at")
    search_fields = ("original_filename", "asset__name", "customer__name", "sha256")
    readonly_fields = tuple(field.name for field in AssetVersion._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AssetAnalysis)
class AssetAnalysisAdmin(admin.ModelAdmin):
    list_display = ("public_id", "version", "image_width", "image_height", "analyzed_at")
    list_filter = ("analyzed_at",)
    search_fields = ("version__original_filename", "customer__name")
    readonly_fields = tuple(field.name for field in AssetAnalysis._meta.fields)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OrderUpload)
class OrderUploadAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "uploaded_by",
        "original_filename",
        "mime_type",
        "size_bytes",
        "drive_sync_status",
        "created_at",
    )
    list_filter = ("mime_type", "created_at")
    search_fields = ("original_filename", "order__customer__name")
    readonly_fields = (
        "public_id",
        "order",
        "uploaded_by",
        "original_filename",
        "mime_type",
        "size_bytes",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order", "uploaded_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.display(description="Drive sync")
    def drive_sync_status(self, obj):
        drive_sync = getattr(obj, "drive_sync", None)
        if drive_sync is None:
            return "-"
        return drive_sync.status


@admin.register(OrderUploadInspection)
class OrderUploadInspectionAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order_upload",
        "status",
        "file_kind",
        "image_width",
        "image_height",
        "checked_at",
    )
    list_filter = ("status", "file_kind", "checked_at")
    search_fields = (
        "order_upload__original_filename",
        "order_upload__order__customer__name",
        "summary_message",
    )
    readonly_fields = (
        "public_id",
        "order_upload",
        "status",
        "summary_message",
        "file_kind",
        "file_extension",
        "image_width",
        "image_height",
        "metadata",
        "checked_at",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order_upload",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OrderDriveFolder)
class OrderDriveFolderAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order",
        "shared_drive_id",
        "order_folder_id",
        "relative_path",
        "created_at",
    )
    search_fields = ("order__public_id", "order__customer__name", "order_folder_id")
    readonly_fields = (
        "public_id",
        "order",
        "shared_drive_id",
        "relative_path",
        "order_folder_id",
        "folder_ids",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(OrderUploadDriveSync)
class OrderUploadDriveSyncAdmin(admin.ModelAdmin):
    list_display = (
        "public_id",
        "order_upload",
        "status",
        "drive_file_id",
        "last_attempt_at",
        "synced_at",
    )
    list_filter = ("status", "last_attempt_at", "synced_at")
    search_fields = (
        "order_upload__original_filename",
        "order_upload__order__customer__name",
        "drive_file_id",
        "last_error",
    )
    readonly_fields = (
        "public_id",
        "order_upload",
        "drive_folder",
        "status",
        "remote_folder_id",
        "drive_file_id",
        "drive_filename",
        "last_error",
        "attempt_count",
        "last_attempt_at",
        "synced_at",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    autocomplete_fields = ("order_upload", "drive_folder")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
