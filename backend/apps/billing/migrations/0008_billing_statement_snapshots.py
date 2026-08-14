from django.db import migrations, models


def require_legacy_statement_reconciliation(apps, schema_editor):
    statement_model = apps.get_model("billing", "BillingStatement")
    if statement_model.objects.exists():
        raise RuntimeError(
            "Migration interrompue : des relevés historiques existent sans snapshot comptable. "
            "Exportez et réconciliez-les manuellement, puis supprimez-les avant de relancer "
            "cette migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0007_billing_statement_period_constraints"),
    ]

    operations = [
        migrations.RunPython(
            require_legacy_statement_reconciliation,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name="billingstatement",
            name="snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Snapshot immuable des données exportées vers l’outil comptable.",
            ),
        ),
        migrations.AddField(
            model_name="billingstatement",
            name="snapshot_sha256",
            field=models.CharField(
                blank=True,
                help_text="Empreinte SHA-256 du CSV canonique associé au snapshot.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="billingstatement",
            name="issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RemoveConstraint(
            model_name="billingstatement",
            name="uniq_customer_billing_statement_period",
        ),
        migrations.AddConstraint(
            model_name="billingstatement",
            constraint=models.UniqueConstraint(
                fields=("customer", "period_start"),
                name="uniq_customer_billing_statement_month",
            ),
        ),
    ]
