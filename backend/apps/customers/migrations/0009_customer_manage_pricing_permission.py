# Generated manually — permission manage_customer_pricing.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0008_customer_siren_customer_vat_number_and_more"),
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
