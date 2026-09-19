from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0011_payment_single_payable_or_captured"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="source",
            field=models.CharField(default="backend_capture", max_length=64),
        ),
    ]
