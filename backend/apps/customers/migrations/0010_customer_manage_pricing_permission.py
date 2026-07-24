# Generated manually — permission manage_customer_pricing.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0009_customer_preferred_settlement_stripe"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="customer",
            options={
                "ordering": ("name",),
                "permissions": [
                    (
                        "manage_customer_pricing",
                        "Peut définir les conditions tarifaires d’un compte client",
                    ),
                ],
            },
        ),
    ]
