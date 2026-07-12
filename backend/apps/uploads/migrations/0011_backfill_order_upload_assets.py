from django.db import migrations


def backfill_order_upload_assets(apps, schema_editor):
    Asset = apps.get_model("uploads", "Asset")
    AssetVersion = apps.get_model("uploads", "AssetVersion")
    OrderUpload = apps.get_model("uploads", "OrderUpload")

    uploads = OrderUpload.objects.filter(asset_version__isnull=True).select_related("order")
    for upload in uploads.iterator(chunk_size=500):
        asset = Asset.objects.create(
            customer_id=upload.order.customer_id,
            created_by_id=upload.uploaded_by_id,
            name=upload.original_filename,
        )
        version = AssetVersion.objects.create(
            customer_id=upload.order.customer_id,
            asset_id=asset.id,
            uploaded_by_id=upload.uploaded_by_id,
            version_number=1,
            file=upload.file.name,
            original_filename=upload.original_filename,
            mime_type=upload.mime_type,
            size_bytes=upload.size_bytes,
            sha256="",
            analysis_status="pending",
        )
        asset.current_version_id = version.id
        asset.save(update_fields=["current_version"])
        upload.asset_version_id = version.id
        upload.save(update_fields=["asset_version"])


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0010_asset_assetversion_assetanalysis_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_order_upload_assets, migrations.RunPython.noop),
    ]
