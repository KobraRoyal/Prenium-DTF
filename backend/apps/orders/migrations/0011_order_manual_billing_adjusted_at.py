from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0010_order_estimated_handover_date"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="manual_billing_adjusted_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Ajustement Atelier (encours) : qté / PU / port figés. "
                    "Exclut la commande du recalcul de remise volume mensuel ; "
                    "un nouveau calcul depuis le métrage efface ce gel."
                ),
                null=True,
            ),
        ),
    ]
