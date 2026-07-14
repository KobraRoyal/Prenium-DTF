from django.db import migrations, models

import apps.uploads.models


class Migration(migrations.Migration):
    dependencies = [("uploads", "0012_assetversion_auto_size_requested")]

    operations = [
        migrations.AddField(
            model_name="assetanalysis",
            name="thin_zone_overlay",
            field=models.FileField(
                blank=True,
                max_length=500,
                upload_to=apps.uploads.models.asset_thin_zone_overlay_path,
            ),
        ),
    ]
