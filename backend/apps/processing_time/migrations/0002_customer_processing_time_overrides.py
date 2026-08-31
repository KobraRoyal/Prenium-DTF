import django.core.validators
import django.db.models.deletion
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0001_initial"),
        ("processing_time", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerProcessingTimeOptionOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                (
                    "markup_percent",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Majoration % sur DTF. Vide = grille par défaut.",
                        max_digits=5,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "flat_fee_eur",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Forfait HT. Vide = grille par défaut.",
                        max_digits=10,
                        null=True,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Décochez pour masquer cette option au client.",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="processing_time_overrides",
                        to="customers.customer",
                    ),
                ),
                (
                    "option",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="customer_overrides",
                        to="processing_time.processingtimeoption",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="customerprocessingtimeoptionoverride",
            index=models.Index(fields=["customer", "option"], name="proc_time_cust_opt_idx"),
        ),
        migrations.AddConstraint(
            model_name="customerprocessingtimeoptionoverride",
            constraint=models.UniqueConstraint(
                fields=("customer", "option"),
                name="proc_time_cust_option_uniq",
            ),
        ),
    ]
