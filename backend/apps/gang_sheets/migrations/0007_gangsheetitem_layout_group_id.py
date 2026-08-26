from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("gang_sheets", "0006_gangsheet_axis_spacing")]

    operations = [
        migrations.AddField(
            model_name="gangsheetitem",
            name="layout_group_id",
            field=models.UUIDField(
                blank=True,
                db_index=True,
                help_text="Identifiant de groupe de composition (déplacement et centrage solidaires).",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="gangsheetitem",
            index=models.Index(
                fields=("sheet", "layout_group_id"),
                name="gangitem_sheet_group_idx",
            ),
        ),
    ]
