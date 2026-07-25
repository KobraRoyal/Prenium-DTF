from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0011_customer_b2b_projects_default_all"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="default_billing_mode",
            field=models.CharField(
                choices=[
                    ("deferred", "Encours / facturation différée"),
                    ("immediate", "Paiement comptant (carte bancaire)"),
                ],
                default="deferred",
                help_text=(
                    "Préselection à la transmission des commandes B2B : "
                    "encours (facturation différée) ou comptant carte bancaire. "
                    "Le client peut encore choisir commande par commande."
                ),
                max_length=16,
                verbose_name="Mode de règlement par défaut",
            ),
        ),
    ]
