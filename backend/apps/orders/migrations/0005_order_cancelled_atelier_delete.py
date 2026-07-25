# Generated manually for soft-delete Atelier orders

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0004_sync_labels"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("submitted", "Submitted"),
                    ("cancelled", "Cancelled"),
                ],
                default="submitted",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="cancellation_reason",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterModelOptions(
            name="order",
            options={
                "ordering": ("-created_at",),
                "permissions": [
                    ("delete_atelier_order", "Peut supprimer une commande Atelier"),
                ],
            },
        ),
    ]
