import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0011_workshop_web_push"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserEmailNotificationMute",
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
                    "event",
                    models.CharField(
                        choices=[
                            ("order_created", "Commande créée"),
                            ("order_processing", "Commande en traitement"),
                            ("order_ready_to_ship", "Commande traitée"),
                            ("order_ready_for_pickup", "Commande prête au retrait"),
                            ("order_shipped", "Commande expédiée"),
                            ("order_priced", "Commande tarifée"),
                            ("volume_discount_tier_reached", "Palier de remise atteint"),
                        ],
                        max_length=48,
                        verbose_name="Événement",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="email_notification_mutes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Préférence e-mail",
                "verbose_name_plural": "Préférences e-mail",
            },
        ),
        migrations.AddIndex(
            model_name="useremailnotificationmute",
            index=models.Index(fields=["event"], name="notif_email_mute_event_idx"),
        ),
        migrations.AddConstraint(
            model_name="useremailnotificationmute",
            constraint=models.UniqueConstraint(
                fields=("user", "event"),
                name="uniq_user_email_notification_mute",
            ),
        ),
    ]
