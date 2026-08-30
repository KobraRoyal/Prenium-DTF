import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_billing_statement_freeze"),
        ("processing_time", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="processing_time_code",
            field=models.SlugField(
                blank=True,
                help_text="Snapshot code délai de traitement (standard / fast / express).",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="processing_time_name",
            field=models.CharField(
                blank=True,
                help_text="Snapshot libellé délai de traitement au moment du choix.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="processing_time_markup_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Majoration % sur DTF figée au choix client.",
                max_digits=5,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="processing_time_markup_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Montant HT de la majoration % sur DTF.",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="processing_time_flat_fee",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Forfait HT express figé au choix client.",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="processing_time_surcharge_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Total HT majoration délai (markup + forfait).",
                max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
    ]
