# Generated manually for Lot 2 — link pick scan → PodUnit

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0007_pod_pick_session"),
    ]

    operations = [
        migrations.AddField(
            model_name="podpicksessionline",
            name="unit",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pick_line",
                to="pod.podunit",
            ),
        ),
    ]
