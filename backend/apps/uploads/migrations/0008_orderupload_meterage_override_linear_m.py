from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0007_orderupload_meterage_override_sqm"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderupload",
            name="meterage_override_linear_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Saisie opérateur : mètres linéaires le long de la laize (par exemplaire). m² = linéaire × laize × quantité.",
                max_digits=12,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.0001")),
                ],
            ),
        ),
    ]
