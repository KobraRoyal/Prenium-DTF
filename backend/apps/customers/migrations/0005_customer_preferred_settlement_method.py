# Generated manually — mode de règlement par client.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0004_customer_addresses_shipping_file_prep_fee"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="preferred_settlement_method",
            field=models.CharField(
                choices=[("paypal", "PayPal"), ("wire_transfer", "Virement bancaire")],
                default="wire_transfer",
                help_text="PayPal (paiement en ligne) ou virement — utilisé comme référence comptable / UI.",
                max_length=24,
                verbose_name="Mode de règlement préféré",
            ),
        ),
    ]
