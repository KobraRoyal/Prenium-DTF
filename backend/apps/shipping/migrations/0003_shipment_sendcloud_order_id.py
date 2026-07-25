from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shipping", "0002_shipment_shipped_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="shipment",
            name="sendcloud_order_id",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="shipment",
            name="shipping_option_code",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Indication transporteur / service (optionnelle) ; "
                    "l’étiquette est créée dans Sendcloud."
                ),
                max_length=128,
            ),
        ),
        migrations.AddIndex(
            model_name="shipment",
            index=models.Index(
                fields=["sendcloud_order_id"],
                name="shipping_sh_sendclo_6f3a91_idx",
            ),
        ),
    ]
