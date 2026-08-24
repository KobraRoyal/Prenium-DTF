from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0004_productionprintrecord_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="productionjob",
            name="of_document_issued_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Horodatage de la première émission PDF OF depuis la tour de contrôle.",
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name="productionjob",
            index=models.Index(
                fields=["of_document_issued_at", "status"],
                name="production__of_doc_i_6f2a1b_idx",
            ),
        ),
    ]
