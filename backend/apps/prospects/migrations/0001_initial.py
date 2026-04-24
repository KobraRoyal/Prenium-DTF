# Generated manually for ProspectProfile

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0003_alter_user_options_user_staff_mfa_enabled_and_more"),
        ("customers", "0002_remove_customer_primary_contact_customermembership"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProspectProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("first_name", models.CharField(max_length=150)),
                ("last_name", models.CharField(max_length=150)),
                ("email", models.EmailField(db_index=True, max_length=254)),
                ("phone", models.CharField(max_length=32)),
                ("company", models.CharField(max_length=255)),
                ("country", models.CharField(max_length=2)),
                ("activity_type", models.CharField(max_length=32)),
                ("service_interest", models.CharField(max_length=32)),
                ("main_goal", models.CharField(blank=True, max_length=500)),
                ("project_timing", models.CharField(max_length=32)),
                ("monthly_volume", models.CharField(max_length=16)),
                ("order_frequency", models.CharField(max_length=16)),
                ("urgency", models.CharField(max_length=16)),
                (
                    "status",
                    models.CharField(
                        db_index=True,
                        default="new",
                        max_length=32,
                    ),
                ),
                ("source", models.CharField(default="tunnel_web", max_length=64)),
                (
                    "customer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="prospect_profiles",
                        to="customers.customer",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="prospect_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="prospectprofile",
            index=models.Index(fields=["status", "created_at"], name="prospects_p_status_7f8a9c_idx"),
        ),
        migrations.AddIndex(
            model_name="prospectprofile",
            index=models.Index(fields=["email"], name="prospects_p_email_2b3c4d_idx"),
        ),
    ]
