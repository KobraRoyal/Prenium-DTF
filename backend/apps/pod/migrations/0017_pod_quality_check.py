import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0016_shopify_line_identity"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PodQualityCheck",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "public_id",
                    models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[("pass", "Conforme"), ("fail", "Refusé")], max_length=8
                    ),
                ),
                ("defect_code", models.CharField(blank=True, default="", max_length=80)),
                ("note", models.CharField(blank=True, default="", max_length=500)),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.AlterField(
            model_name="podunit",
            name="status",
            field=models.CharField(
                choices=[
                    ("waiting_press", "Attente pose"),
                    ("pressed", "Posé"),
                    ("qc_passed", "Contrôle validé"),
                    ("qc_failed", "Contrôle refusé"),
                    ("issue", "Incident"),
                ],
                default="waiting_press",
                max_length=24,
            ),
        ),
        migrations.AddIndex(
            model_name="podunit",
            index=models.Index(fields=["status", "created_at"], name="pod_unit_qc_queue_idx"),
        ),
        migrations.AddField(
            model_name="podqualitycheck",
            name="checked_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="pod_quality_checks",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="podqualitycheck",
            name="unit",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="quality_checks",
                to="pod.podunit",
            ),
        ),
        migrations.AddIndex(
            model_name="podqualitycheck",
            index=models.Index(fields=["unit", "created_at"], name="pod_qc_unit_created_idx"),
        ),
    ]
