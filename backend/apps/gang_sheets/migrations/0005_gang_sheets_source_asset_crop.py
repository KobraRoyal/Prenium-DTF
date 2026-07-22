from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gang_sheets", "0004_gangsheetdrivesync")]

    operations = [
        migrations.AddField(
            model_name="gangsheetsourceasset",
            name="crop_height",
            field=models.DecimalField(decimal_places=6, default=Decimal("1"), max_digits=7),
        ),
        migrations.AddField(
            model_name="gangsheetsourceasset",
            name="crop_width",
            field=models.DecimalField(decimal_places=6, default=Decimal("1"), max_digits=7),
        ),
        migrations.AddField(
            model_name="gangsheetsourceasset",
            name="crop_x",
            field=models.DecimalField(decimal_places=6, default=Decimal("0"), max_digits=7),
        ),
        migrations.AddField(
            model_name="gangsheetsourceasset",
            name="crop_y",
            field=models.DecimalField(decimal_places=6, default=Decimal("0"), max_digits=7),
        ),
        migrations.AddConstraint(
            model_name="gangsheetsourceasset",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    crop_height__gte=Decimal("0.01"),
                    crop_height__lte=1,
                    crop_width__gte=Decimal("0.01"),
                    crop_width__lte=1,
                    crop_x__gte=0,
                    crop_x__lte=1,
                    crop_y__gte=0,
                    crop_y__lte=1,
                ),
                name="gang_source_crop_unit_bounds",
            ),
        ),
        migrations.AddConstraint(
            model_name="gangsheetsourceasset",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_x__lte=Decimal("1") - models.F("crop_width")),
                name="gang_source_crop_x_extent",
            ),
        ),
        migrations.AddConstraint(
            model_name="gangsheetsourceasset",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_y__lte=Decimal("1") - models.F("crop_height")),
                name="gang_source_crop_y_extent",
            ),
        ),
    ]
