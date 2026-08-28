from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("gang_sheets", "0007_gangsheetitem_layout_group_id")]

    operations = [
        migrations.AddField(
            model_name="gangsheetitem",
            name="kind",
            field=models.CharField(
                choices=[("visual", "Visuel"), ("text", "Texte")],
                default="visual",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="gangsheetitem",
            name="text_align",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AddField(
            model_name="gangsheetitem",
            name="text_bold",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="gangsheetitem",
            name="text_color",
            field=models.CharField(blank=True, max_length=7),
        ),
        migrations.AddField(
            model_name="gangsheetitem",
            name="text_content",
            field=models.CharField(blank=True, max_length=200),
        ),
        migrations.AddField(
            model_name="gangsheetitem",
            name="text_font",
            field=models.CharField(blank=True, max_length=16),
        ),
        migrations.AlterField(
            model_name="gangsheetitem",
            name="asset_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="gang_sheet_items",
                to="uploads.assetversion",
            ),
        ),
        migrations.AddIndex(
            model_name="gangsheetitem",
            index=models.Index(
                fields=("customer", "sheet", "kind"),
                name="gangitem_sheet_kind_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="gangsheetitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        kind="visual",
                        asset_version__isnull=False,
                        text_content="",
                    )
                    | (
                        models.Q(kind="text", asset_version__isnull=True)
                        & ~models.Q(text_content="")
                    )
                ),
                name="gangitem_kind_payload",
            ),
        ),
    ]
