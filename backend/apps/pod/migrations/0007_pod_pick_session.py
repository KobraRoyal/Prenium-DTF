import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("pod", "0006_shopify_oauth_rip_drive"),
    ]

    operations = [
        migrations.CreateModel(
            name="PodPickSession",
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
                    models.UUIDField(
                        db_index=True, default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                ("code", models.CharField(max_length=32, unique=True)),
                ("piece_count", models.PositiveIntegerField(default=0)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pod_pick_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="PodPickSessionLine",
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
                    models.UUIDField(
                        db_index=True, default=uuid.uuid4, editable=False, unique=True
                    ),
                ),
                ("sequence", models.PositiveIntegerField(default=1)),
                ("scan_identifier", models.CharField(db_index=True, max_length=32, unique=True)),
                ("shopify_order_number", models.CharField(max_length=64)),
                ("shopify_sku", models.CharField(blank=True, default="", max_length=80)),
                ("blank_name", models.CharField(blank=True, default="", max_length=160)),
                ("blank_sku", models.CharField(blank=True, default="", max_length=80)),
                ("size_label", models.CharField(blank=True, default="", max_length=32)),
                ("color_name", models.CharField(blank=True, default="", max_length=64)),
                ("location_code", models.CharField(blank=True, default="", max_length=64)),
                ("markings", models.CharField(blank=True, default="", max_length=255)),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="pod.podpicksession",
                    ),
                ),
                (
                    "work_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pick_lines",
                        to="pod.podripworkitem",
                    ),
                ),
            ],
            options={
                "ordering": ("location_code", "blank_sku", "shopify_order_number", "sequence"),
            },
        ),
        migrations.AddConstraint(
            model_name="podpicksessionline",
            constraint=models.UniqueConstraint(
                fields=("work_item", "sequence"),
                name="pod_pick_line_work_item_sequence_uniq",
            ),
        ),
    ]
