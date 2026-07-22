from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


def copy_legacy_spacing(apps, _schema_editor):
    GangSheet = apps.get_model("gang_sheets", "GangSheet")
    for sheet in GangSheet.objects.only("pk", "item_spacing_mm").iterator():
        GangSheet.objects.filter(pk=sheet.pk).update(
            item_spacing_x_mm=sheet.item_spacing_mm,
            item_spacing_y_mm=sheet.item_spacing_mm,
        )


class Migration(migrations.Migration):
    dependencies = [("gang_sheets", "0005_gang_sheets_source_asset_crop")]

    operations = [
        migrations.AddField(
            model_name="gangsheet",
            name="item_spacing_x_mm",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=6,
                validators=[
                    MinValueValidator(Decimal("0.00")),
                    MaxValueValidator(Decimal("100.00")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="gangsheet",
            name="item_spacing_y_mm",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=6,
                validators=[
                    MinValueValidator(Decimal("0.00")),
                    MaxValueValidator(Decimal("100.00")),
                ],
            ),
        ),
        migrations.RunPython(copy_legacy_spacing, migrations.RunPython.noop),
    ]
