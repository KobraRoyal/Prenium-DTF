from django.contrib import admin

from apps.gang_sheets.models import (
    GangSheet,
    GangSheetDriveSync,
    GangSheetItem,
    GangSheetSiteSettings,
    GangSheetSourceAsset,
)


@admin.register(GangSheetSiteSettings)
class GangSheetSiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("roll_width_mm", "margin_mm", "item_spacing_mm", "updated_at")
    readonly_fields = ("public_id", "updated_by")

    def has_add_permission(self, request):
        return not GangSheetSiteSettings.objects.exists()


class GangSheetItemInline(admin.TabularInline):
    model = GangSheetItem
    extra = 0
    readonly_fields = ("public_id", "customer", "asset_version")


class GangSheetSourceAssetInline(admin.TabularInline):
    model = GangSheetSourceAsset
    extra = 0
    readonly_fields = (
        "public_id",
        "customer",
        "asset",
        "width_mm",
        "height_mm",
        "crop_x",
        "crop_y",
        "crop_width",
        "crop_height",
    )


class GangSheetDriveSyncInline(admin.StackedInline):
    model = GangSheetDriveSync
    extra = 0
    can_delete = False
    readonly_fields = (
        "public_id",
        "customer",
        "status",
        "revision",
        "drive_filename",
        "remote_folder_id",
        "drive_file_id",
        "sha256",
        "last_error",
        "last_attempt_at",
        "synced_at",
        "attempt_count",
    )


@admin.register(GangSheet)
class GangSheetAdmin(admin.ModelAdmin):
    list_display = ("name", "customer", "project", "status", "width_mm", "height_mm", "updated_at")
    list_filter = ("status",)
    search_fields = ("name", "customer__name", "project__project_number")
    readonly_fields = (
        "public_id",
        "preview_file",
        "final_file",
        "production_asset",
        "revision",
    )
    inlines = (GangSheetDriveSyncInline, GangSheetSourceAssetInline, GangSheetItemInline)


@admin.register(GangSheetDriveSync)
class GangSheetDriveSyncAdmin(admin.ModelAdmin):
    list_display = (
        "gang_sheet",
        "customer",
        "status",
        "revision",
        "attempt_count",
        "synced_at",
    )
    list_filter = ("status",)
    search_fields = ("gang_sheet__name", "customer__name", "drive_filename")
    readonly_fields = (
        "public_id",
        "customer",
        "gang_sheet",
        "status",
        "revision",
        "drive_filename",
        "remote_folder_id",
        "drive_file_id",
        "sha256",
        "last_error",
        "last_attempt_at",
        "synced_at",
        "attempt_count",
    )
