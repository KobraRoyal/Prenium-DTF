from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0009_pod_rip_work_item_cancelled"),
    ]

    operations = [
        migrations.AddField(
            model_name="podpicksessionline",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
