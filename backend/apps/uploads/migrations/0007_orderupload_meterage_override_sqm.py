# Generated manually

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0006_b2b_deferred_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderupload",
            name="meterage_override_sqm",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Saisie opérateur (m²) — prioritaire sur le calcul inspection pour la facturation.",
                max_digits=12,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.0001")),
                ],
            ),
        ),
    ]
