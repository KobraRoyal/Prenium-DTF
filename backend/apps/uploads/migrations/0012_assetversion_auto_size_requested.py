from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0011_backfill_order_upload_assets"),
    ]

    operations = [
        migrations.AddField(
            model_name="assetversion",
            name="auto_size_requested",
            field=models.BooleanField(
                default=False,
                help_text="Appliquer une fois la taille physique détectée à la ligne projet.",
            ),
        ),
    ]
