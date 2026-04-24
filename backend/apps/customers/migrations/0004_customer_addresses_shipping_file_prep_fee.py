# Generated manually for Prenium DTF — adresses, logistique, forfait fichier négociable.

import django.core.validators
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0003_b2b_deferred_billing"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="billing_address_line1",
            field=models.CharField(blank=True, max_length=255, verbose_name="Facturation — ligne 1"),
        ),
        migrations.AddField(
            model_name="customer",
            name="billing_address_line2",
            field=models.CharField(blank=True, max_length=255, verbose_name="Facturation — ligne 2"),
        ),
        migrations.AddField(
            model_name="customer",
            name="billing_postal_code",
            field=models.CharField(blank=True, max_length=32, verbose_name="Facturation — code postal"),
        ),
        migrations.AddField(
            model_name="customer",
            name="billing_city",
            field=models.CharField(blank=True, max_length=128, verbose_name="Facturation — ville"),
        ),
        migrations.AddField(
            model_name="customer",
            name="billing_country",
            field=models.CharField(
                default="FR",
                max_length=2,
                verbose_name="Facturation — pays (ISO 3166-1 alpha-2)",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="shipping_address_line1",
            field=models.CharField(
                blank=True,
                max_length=255,
                help_text="Par défaut pour expédition / étiquette ; peut être repris sur la commande.",
                verbose_name="Livraison — ligne 1",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="shipping_address_line2",
            field=models.CharField(blank=True, max_length=255, verbose_name="Livraison — ligne 2"),
        ),
        migrations.AddField(
            model_name="customer",
            name="shipping_postal_code",
            field=models.CharField(blank=True, max_length=32, verbose_name="Livraison — code postal"),
        ),
        migrations.AddField(
            model_name="customer",
            name="shipping_city",
            field=models.CharField(blank=True, max_length=128, verbose_name="Livraison — ville"),
        ),
        migrations.AddField(
            model_name="customer",
            name="shipping_country",
            field=models.CharField(
                default="FR",
                max_length=2,
                verbose_name="Livraison — pays (ISO 3166-1 alpha-2)",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="default_shipping_mode",
            field=models.CharField(
                choices=[
                    ("pickup", "Retrait atelier"),
                    ("carrier", "Expédition (transporteur)"),
                    ("direct", "Livraison directe au client"),
                ],
                default="carrier",
                max_length=16,
                verbose_name="Mode d’acheminement par défaut",
            ),
        ),
        migrations.AddField(
            model_name="customer",
            name="negotiated_file_preparation_fee_eur",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Si renseigné : forfait « préparation fichier » par fichier pour ce client. Sinon : prix du service catalogue « Préparation fichier » (ex. 10 €).",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                verbose_name="Forfait préparation fichier négocié (EUR / fichier)",
            ),
        ),
        migrations.AlterField(
            model_name="customerbillingprofile",
            name="price_per_sqm_eur",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="[Obsolète — non utilisé pour le calcul] Ancienne grille au m² par client. Le tarif m² est désormais toujours celui du service catalogue DTF.",
                max_digits=10,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
    ]
