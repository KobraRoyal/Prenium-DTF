from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0006_shipping_methods_and_order_vat"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="monthly_volume_linear_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Volume linéaire mensuel éligible au dernier calcul.",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="volume_discount_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Montant HT de remise volume appliqué au DTF de la commande.",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="volume_discount_base_unit_price_eur",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Prix DTF brut au m² conservé avant remise volume.",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="volume_discount_month",
            field=models.DateField(
                blank=True,
                help_text="Premier jour du mois civil utilisé pour la remise volume.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="volume_discount_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Pourcentage de remise rétroactive appliqué au DTF de la commande.",
                max_digits=5,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="volume_discount_threshold_linear_m",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Seuil du palier mensuel appliqué, si un palier est atteint.",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
    ]
