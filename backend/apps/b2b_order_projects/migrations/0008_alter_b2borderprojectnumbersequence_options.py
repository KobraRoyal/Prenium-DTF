from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0007_rename_preparation_note_to_gang_sheet"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="b2borderprojectnumbersequence",
            options={"verbose_name": "Séquence de numéro Gang Sheet"},
        ),
    ]
