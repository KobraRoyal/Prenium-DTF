import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0008_customer_siren_customer_vat_number_and_more"),
        ("gang_sheets", "0003_gangsheet_production_asset_alter_gangsheet_project_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="GangSheetDriveSync",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "public_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "En attente"),
                            ("synced", "Synchronisé"),
                            ("failed", "Échec"),
                        ],
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("revision", models.PositiveIntegerField(default=0)),
                ("drive_filename", models.CharField(blank=True, max_length=255)),
                ("remote_folder_id", models.CharField(blank=True, max_length=255)),
                ("drive_file_id", models.CharField(blank=True, max_length=255)),
                ("sha256", models.CharField(blank=True, max_length=64)),
                ("last_error", models.CharField(blank=True, max_length=255)),
                ("last_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("synced_at", models.DateTimeField(blank=True, null=True)),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gang_sheet_drive_syncs",
                        to="customers.customer",
                    ),
                ),
                (
                    "gang_sheet",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="drive_sync",
                        to="gang_sheets.gangsheet",
                    ),
                ),
            ],
            options={
                "ordering": ("-updated_at", "-created_at"),
                "indexes": [
                    models.Index(
                        fields=["customer", "status", "updated_at"],
                        name="gang_drive_customer_status_idx",
                    ),
                    models.Index(
                        fields=["status", "last_attempt_at"],
                        name="gang_drive_status_attempt_idx",
                    ),
                ],
            },
        ),
    ]
