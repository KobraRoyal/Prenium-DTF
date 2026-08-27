from decimal import Decimal

from django.db import migrations, models


def backfill_text_size(apps, schema_editor):
    item_model = apps.get_model("gang_sheets", "GangSheetItem")
    ratio = Decimal("0.18")
    min_size = Decimal("2.00")
    max_size = Decimal("80.00")
    for item in item_model.objects.filter(kind="text"):
        size = (item.width_mm * ratio).quantize(Decimal("0.01"))
        item.text_size_mm = min(max_size, max(min_size, size))
        item.save(update_fields=["text_size_mm"])


class Migration(migrations.Migration):
    dependencies = [("gang_sheets", "0008_gangsheetitem_text_kind")]

    operations = [
        migrations.AddField(
            model_name="gangsheetitem",
            name="text_size_mm",
            field=models.DecimalField(decimal_places=2, default=Decimal("12.00"), max_digits=6),
        ),
        migrations.AlterField(
            model_name="gangsheetitem",
            name="text_font",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.RunPython(backfill_text_size, migrations.RunPython.noop),
    ]
