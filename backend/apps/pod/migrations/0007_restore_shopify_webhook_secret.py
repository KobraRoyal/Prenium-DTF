# Répare un écart local fréquent : DB migrée avec 0007 stash (secret chiffré)
# alors que cette branche conserve webhook_secret en clair côté modèle.

import base64
import hashlib

from django.conf import settings
from django.db import migrations, models


def _fernet():
    from cryptography.fernet import Fernet

    configured = (getattr(settings, "SHOPIFY_TOKEN_FERNET_KEY", "") or "").strip()
    if configured:
        key = configured.encode()
    else:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def restore_webhook_secret_column(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'pod_shopifystore' AND column_name = 'webhook_secret'
            """
        )
        if cursor.fetchone():
            return
        cursor.execute(
            """
            ALTER TABLE pod_shopifystore
            ADD COLUMN webhook_secret varchar(128) NOT NULL DEFAULT ''
            """
        )

    ShopifyStore = apps.get_model("pod", "ShopifyStore")
    field_names = {field.name for field in ShopifyStore._meta.get_fields()}
    if "webhook_secret_encrypted" not in field_names:
        return

    cipher = _fernet()
    from cryptography.fernet import InvalidToken

    for store in ShopifyStore.objects.all().order_by("pk"):
        encrypted = getattr(store, "webhook_secret_encrypted", "") or ""
        if not encrypted:
            continue
        try:
            plain = cipher.decrypt(encrypted.encode()).decode()
        except InvalidToken:
            plain = encrypted[:128]
        store.webhook_secret = plain[:128]
        store.save(update_fields=["webhook_secret"])


class Migration(migrations.Migration):

    dependencies = [
        ("pod", "0006_shopify_oauth_rip_drive"),
    ]

    operations = [
        migrations.RunPython(restore_webhook_secret_column, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name="shopifystore",
                    name="webhook_secret",
                    field=models.CharField(
                        blank=True,
                        default="",
                        help_text="Secret HMAC Shopify (jamais exposé en front).",
                        max_length=128,
                    ),
                ),
            ],
        ),
    ]
