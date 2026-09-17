from django.db import migrations, models

import apps.uploads.models
import apps.uploads.validators


class Migration(migrations.Migration):
    dependencies = [("uploads", "0020_orderupload_production_derivative_state")]

    operations = [
        migrations.AlterField(
            model_name="orderupload",
            name="file",
            field=models.FileField(
                upload_to=apps.uploads.models.order_upload_path,
                max_length=500,
                blank=True,
            ),
        ),
        migrations.AlterField(
            model_name="orderupload",
            name="mime_type",
            field=models.CharField(max_length=255, blank=True),
        ),
        migrations.AddField(
            model_name="orderupload",
            name="external_url",
            field=models.URLField(
                max_length=2000,
                blank=True,
                default="",
                validators=[apps.uploads.validators.validate_external_url],
            ),
        ),
        migrations.AddConstraint(
            model_name="orderupload",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(external_url="")
                    | (
                        models.Q(file="")
                        & models.Q(size_bytes=0)
                        & models.Q(asset_version__isnull=True)
                    )
                ),
                name="uploads_external_link_no_local_file",
            ),
        ),
    ]
