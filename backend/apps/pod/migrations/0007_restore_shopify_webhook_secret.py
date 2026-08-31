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


def _table_has_column(schema_editor, table_name: str, column_name: str) -> bool:
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                [table_name, column_name],
            )
            return cursor.fetchone() is not None
        description = connection.introspection.get_table_description(cursor, table_name)
        return any(field.name == column_name for field in description)


def restore_webhook_secret_column(apps, schema_editor):
    table_name = "pod_shopifystore"
    column_name = "webhook_secret"
    if _table_has_column(schema_editor, table_name, column_name):
        return

    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} varchar(128) NOT NULL DEFAULT ''"
        )
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_name} varchar(128) NOT NULL DEFAULT ''"
        )
    else:
        return

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
