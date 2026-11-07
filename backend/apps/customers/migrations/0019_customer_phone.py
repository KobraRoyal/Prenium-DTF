from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0018_volumediscountdashboardcopy"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="phone",
            field=models.CharField(
                blank=True,
                help_text="Contact pour l’expédition Sendcloud et les échanges atelier.",
                max_length=32,
                verbose_name="Téléphone",
            ),
        ),
    ]
