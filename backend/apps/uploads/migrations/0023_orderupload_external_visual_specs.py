from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("uploads", "0022_external_visual_count"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderupload",
            name="external_visual_specs",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Déclaration client pour un lien à plusieurs visuels : "
                    "quantité et couleur de support de chacun. Vide si un seul visuel."
                ),
            ),
        ),
    ]
