from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0009_order_line_quantity_precision"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="estimated_handover_date",
            field=models.DateField(
                blank=True,
                help_text=(
                    "Date prévisionnelle de remise : retrait atelier ou livraison, "
                    "selon le mode choisi."
                ),
                null=True,
            ),
        ),
    ]
