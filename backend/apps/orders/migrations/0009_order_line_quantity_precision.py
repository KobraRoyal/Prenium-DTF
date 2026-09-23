from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_billing_statement_freeze"),
    ]

    operations = [
        migrations.AlterField(
            model_name="orderline",
            name="quantity",
            field=models.DecimalField(
                decimal_places=4,
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
    ]
