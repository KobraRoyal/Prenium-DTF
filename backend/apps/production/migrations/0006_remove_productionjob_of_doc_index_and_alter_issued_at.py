from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0005_productionjob_of_document_issued_at"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="productionjob",
            name="production__of_doc_i_6f2a1b_idx",
        ),
        migrations.AlterField(
            model_name="productionjob",
            name="of_document_issued_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Première émission PDF OF depuis la tour de contrôle Atelier.",
                null=True,
            ),
        ),
    ]
