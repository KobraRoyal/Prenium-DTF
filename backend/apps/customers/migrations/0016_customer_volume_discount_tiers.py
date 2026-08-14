from decimal import Decimal
import uuid

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0015_shipping_methods_and_order_vat"),
    ]

    operations = [
        migrations.CreateModel(
            name="CustomerVolumeDiscountTier",
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
                (
                    "public_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "minimum_monthly_linear_m",
                    models.DecimalField(
                        decimal_places=4,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.0001"))],
                        verbose_name="Seuil mensuel (m linéaires)",
                    ),
                ),
                (
                    "discount_percent",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=5,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01")),
                            django.core.validators.MaxValueValidator(Decimal("100.00")),
                        ],
                        verbose_name="Remise (%)",
                    ),
                ),
                ("is_active", models.BooleanField(default=True, verbose_name="Palier actif")),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="volume_discount_tiers",
                        to="customers.customer",
                    ),
                ),
            ],
            options={
                "ordering": ("minimum_monthly_linear_m", "created_at"),
            },
        ),
        migrations.AddConstraint(
            model_name="customervolumediscounttier",
            constraint=models.UniqueConstraint(
                fields=("customer", "minimum_monthly_linear_m"),
                name="uniq_customer_volume_discount_threshold",
            ),
        ),
        migrations.AddConstraint(
            model_name="customervolumediscounttier",
            constraint=models.CheckConstraint(
                condition=models.Q(("minimum_monthly_linear_m__gt", 0)),
                name="customer_volume_discount_threshold_positive",
            ),
        ),
        migrations.AddConstraint(
            model_name="customervolumediscounttier",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("discount_percent__gt", 0),
                    ("discount_percent__lte", Decimal("100.00")),
                ),
                name="customer_volume_discount_percent_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="customervolumediscounttier",
            index=models.Index(
                fields=["customer", "is_active", "minimum_monthly_linear_m"],
                name="cust_vol_tier_lookup_idx",
            ),
        ),
    ]
