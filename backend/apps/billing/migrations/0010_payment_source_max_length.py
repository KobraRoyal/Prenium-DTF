from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_payment_gateway_settings"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="source",
            field=models.CharField(default="client_api", max_length=64),
        ),
    ]
