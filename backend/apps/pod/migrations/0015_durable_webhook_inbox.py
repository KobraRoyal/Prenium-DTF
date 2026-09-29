from django.db import migrations, models


def normalize_historical_duplicate_ids(apps, _schema_editor):
    receipt_model = apps.get_model("pod", "ShopifyWebhookReceipt")
    seen = set()
    for receipt in receipt_model.objects.order_by(
        "webhook_id", "created_at", "pk"
    ).iterator():
        key = receipt.webhook_id
        if key in seen:
            receipt.webhook_id = f"legacy-duplicate-{receipt.pk}"
            receipt.last_error = "Ancien reçu avec ID de livraison déjà présent."
            receipt.save(update_fields=["webhook_id", "last_error"])
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [("pod", "0014_rip_asset_provenance_and_customer_scope")]

    operations = [
        migrations.AddField(
            model_name="shopifywebhookreceipt",
            name="raw_body",
            field=models.BinaryField(blank=True, default=bytes),
        ),
        migrations.AddField(
            model_name="shopifywebhookreceipt",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "En attente"),
                    ("processed", "Traité"),
                    ("failed", "À rejouer"),
                ],
                default="processed",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="shopifywebhookreceipt",
            name="attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="shopifywebhookreceipt",
            name="next_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shopifywebhookreceipt",
            name="processed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shopifywebhookreceipt",
            name="last_error",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.RunPython(normalize_historical_duplicate_ids, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="shopifywebhookreceipt",
            name="pod_webhook_receipt_shop_topic_id_uniq",
        ),
        migrations.AddConstraint(
            model_name="shopifywebhookreceipt",
            constraint=models.UniqueConstraint(
                fields=("webhook_id",),
                name="pod_webhook_receipt_id_uniq",
            ),
        ),
    ]
