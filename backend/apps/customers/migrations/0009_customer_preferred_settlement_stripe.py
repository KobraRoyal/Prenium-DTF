# Generated manually — Stripe settlement preference.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0008_customer_siren_customer_vat_number_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customer",
            name="preferred_settlement_method",
            field=models.CharField(
                choices=[
                    ("paypal", "PayPal"),
                    ("stripe", "Stripe (carte)"),
                    ("wire_transfer", "Virement bancaire"),
                ],
                default="wire_transfer",
                help_text=(
                    "PayPal / Stripe (paiement en ligne immédiat) ou virement — "
                    "hors facturation mensuelle différée."
                ),
                max_length=24,
                verbose_name="Mode de règlement préféré",
            ),
        ),
    ]
