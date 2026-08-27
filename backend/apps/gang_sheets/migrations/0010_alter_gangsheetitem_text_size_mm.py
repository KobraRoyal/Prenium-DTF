from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("gang_sheets", "0009_gangsheetitem_text_size_and_fonts"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gangsheetitem",
            name="text_size_mm",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("12.00"),
                max_digits=6,
                validators=[MinValueValidator(Decimal("2.00"))],
            ),
        ),
    ]
