from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pod", "0005_shopify_webhook_receipt"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopifystore",
            name="access_token_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="shopifystore",
            name="connected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="shopifystore",
            name="oauth_scopes",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="shopifystore",
            name="token_suffix",
            field=models.CharField(blank=True, default="", max_length=8),
        ),
        migrations.AddField(
            model_name="podriplot",
            name="drive_error",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="podriplot",
            name="drive_file_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="podriplot",
            name="drive_folder_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddField(
            model_name="podriplot",
            name="drive_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
