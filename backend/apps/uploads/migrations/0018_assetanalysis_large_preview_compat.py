from django.db import migrations, models

import apps.uploads.models


def ensure_large_preview_column(apps, schema_editor):
    """Ajoute la colonne seulement si une base issue d'une autre branche ne l'a pas déjà."""
    asset_analysis = apps.get_model("uploads", "AssetAnalysis")
    table_name = asset_analysis._meta.db_table
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor,
                table_name,
            )
        }
    if "large_preview" in columns:
        return

    field = models.FileField(blank=True, max_length=500)
    field.set_attributes_from_name("large_preview")
    field.model = asset_analysis
    schema_editor.add_field(asset_analysis, field)


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0017_orderupload_asset_version_fk"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    ensure_large_preview_column,
                    reverse_code=migrations.RunPython.noop,
                )
            ],
            state_operations=[
                migrations.AddField(
                    model_name="assetanalysis",
                    name="large_preview",
                    field=models.FileField(
                        blank=True,
                        max_length=500,
                        upload_to=apps.uploads.models.asset_large_preview_path,
                    ),
                )
            ],
        )
    ]
