from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0004_b2borderprojectitem_support_color_hex"),
    ]

    operations = [
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="crop_mode",
            field=models.CharField(
                choices=[("manual", "Manuel"), ("auto", "Automatique")],
                default="manual",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="crop_x",
            field=models.DecimalField(decimal_places=6, default=Decimal("0"), max_digits=7),
        ),
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="crop_y",
            field=models.DecimalField(decimal_places=6, default=Decimal("0"), max_digits=7),
        ),
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="crop_width",
            field=models.DecimalField(decimal_places=6, default=Decimal("1"), max_digits=7),
        ),
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="crop_height",
            field=models.DecimalField(decimal_places=6, default=Decimal("1"), max_digits=7),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_x__gte=0, crop_x__lte=1),
                name="b2b_item_crop_x_unit",
            ),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_y__gte=0, crop_y__lte=1),
                name="b2b_item_crop_y_unit",
            ),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_width__gte=Decimal("0.01"), crop_width__lte=1),
                name="b2b_item_crop_width_unit",
            ),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_height__gte=Decimal("0.01"), crop_height__lte=1),
                name="b2b_item_crop_height_unit",
            ),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_x__lte=Decimal("1") - models.F("crop_width")),
                name="b2b_item_crop_x_extent",
            ),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=models.Q(crop_y__lte=Decimal("1") - models.F("crop_height")),
                name="b2b_item_crop_y_extent",
            ),
        ),
    ]
