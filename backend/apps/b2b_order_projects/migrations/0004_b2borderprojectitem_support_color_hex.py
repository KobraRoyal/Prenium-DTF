from django.core.validators import RegexValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0003_item_client_analysis_confirmation"),
    ]

    operations = [
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="support_color_hex",
            field=models.CharField(
                blank=True,
                default="",
                max_length=16,
                validators=[
                    RegexValidator(
                        regex=r"^$|^#[0-9A-Fa-f]{6}$|^#multicolor$",
                        message="Couleur support : #RRGGBB ou #multicolor attendu.",
                    )
                ],
            ),
        ),
    ]
