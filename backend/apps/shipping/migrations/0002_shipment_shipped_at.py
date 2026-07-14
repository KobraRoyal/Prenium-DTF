from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shipping", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="shipment",
            name="shipped_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
