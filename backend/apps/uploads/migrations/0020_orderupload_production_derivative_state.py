from django.db import migrations, models


class Migration(migrations.Migration):
    """Restaure les champs dérivé production sur OrderUpload."""

    dependencies = [
        ("uploads", "0019_legacy_b2b_item_fk_cascade"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderupload",
            name="is_production_derivative",
            field=models.BooleanField(
                default=False,
                help_text="Le fichier remis à l'atelier est dérivé de la source client immuable.",
            ),
        ),
        migrations.AddField(
            model_name="orderupload",
            name="production_file_sha256",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="orderupload",
            name="source_crop_metadata",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
