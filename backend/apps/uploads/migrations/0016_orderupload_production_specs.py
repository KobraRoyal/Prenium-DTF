from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.db import migrations, models


def backfill_production_specs(apps, schema_editor):
    OrderUpload = apps.get_model("uploads", "OrderUpload")
    ProjectItem = apps.get_model("b2b_order_projects", "B2BOrderProjectItem")
    pending_updates = []

    uploads = OrderUpload.objects.exclude(asset_version_id=None).iterator(chunk_size=500)
    for upload in uploads:
        source_item = (
            ProjectItem.objects.filter(
                project__converted_order_id=upload.order_id,
                client_confirmed_asset_version_id=upload.asset_version_id,
            )
            .only("width_mm", "height_mm", "support_color_hex")
            .first()
        )
        if source_item is None:
            continue
        upload.width_mm = source_item.width_mm
        upload.height_mm = source_item.height_mm
        if not upload.support_color_hex and source_item.support_color_hex:
            upload.support_color_hex = source_item.support_color_hex
        pending_updates.append(upload)
        if len(pending_updates) >= 500:
            OrderUpload.objects.bulk_update(
                pending_updates,
                ["width_mm", "height_mm", "support_color_hex"],
            )
            pending_updates = []

    if pending_updates:
        OrderUpload.objects.bulk_update(
            pending_updates,
            ["width_mm", "height_mm", "support_color_hex"],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0004_b2borderprojectitem_support_color_hex"),
        ("uploads", "0015_orderuploadreview"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderupload",
            name="width_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AddField(
            model_name="orderupload",
            name="height_mm",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                validators=[MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AlterField(
            model_name="orderupload",
            name="support_color_hex",
            field=models.CharField(
                blank=True,
                max_length=16,
                validators=[
                    RegexValidator(
                        regex=r"^$|^#[0-9A-Fa-f]{6}$|^#multicolor$",
                        message="Couleur attendue au format #RRVVBB ou #multicolor.",
                    )
                ],
            ),
        ),
        migrations.RunPython(backfill_production_specs, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="orderupload",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(width_mm__isnull=True, height_mm__isnull=True)
                    | models.Q(width_mm__isnull=False, height_mm__isnull=False)
                ),
                name="uploads_orderupload_dimensions_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderupload",
            constraint=models.CheckConstraint(
                condition=models.Q(width_mm__isnull=True) | models.Q(width_mm__gt=0),
                name="uploads_orderupload_width_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderupload",
            constraint=models.CheckConstraint(
                condition=models.Q(height_mm__isnull=True) | models.Q(height_mm__gt=0),
                name="uploads_orderupload_height_positive",
            ),
        ),
    ]
