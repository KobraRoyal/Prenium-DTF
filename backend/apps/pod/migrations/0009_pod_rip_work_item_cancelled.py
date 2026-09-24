from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0008_pod_pick_line_unit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="podripworkitem",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "En file RIP"),
                    ("included", "Inclus dans un lot"),
                    ("skipped", "Ignoré (config incomplète)"),
                    ("cancelled", "Annulé (Shopify)"),
                ],
                default="queued",
                max_length=16,
            ),
        ),
    ]
