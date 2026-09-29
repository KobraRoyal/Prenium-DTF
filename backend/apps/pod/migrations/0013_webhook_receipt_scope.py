import secrets

from django.db import migrations, models


def rotate_known_demo_webhook_secret(apps, _schema_editor):
    store_model = apps.get_model("pod", "ShopifyStore")
    for store in store_model.objects.filter(
        shop_domain="demo-boutique.myshopify.com",
        webhook_secret="local-pod-webhook-secret",
    ):
        store.webhook_secret = secrets.token_urlsafe(48)
        store.save(update_fields=["webhook_secret"])


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0012_pod_pick_line_reservation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="shopifywebhookreceipt",
            name="webhook_id",
            field=models.CharField(max_length=128),
        ),
        migrations.AddConstraint(
            model_name="shopifywebhookreceipt",
            constraint=models.UniqueConstraint(
                fields=("shop_domain", "topic", "webhook_id"),
                name="pod_webhook_receipt_shop_topic_id_uniq",
            ),
        ),
        migrations.RunPython(rotate_known_demo_webhook_secret, migrations.RunPython.noop),
    ]
