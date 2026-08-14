from django.db import migrations, models


def validate_existing_statement_periods(apps, schema_editor):
    statement_model = apps.get_model("billing", "BillingStatement")
    duplicates = (
        statement_model.objects.values("customer_id", "period_start")
        .annotate(count=models.Count("id"))
        .filter(count__gt=1)
    )
    if duplicates.exists():
        raise RuntimeError(
            "Migration interrompue : plusieurs relevés existent pour un même client et mois. "
            "Réconciliez-les manuellement avant de relancer la migration."
        )
    if statement_model.objects.filter(period_end__lt=models.F("period_start")).exists():
        raise RuntimeError(
            "Migration interrompue : au moins une période de relevé est inversée. "
            "Corrigez les dates avant de relancer la migration."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0006_sync_labels"),
    ]

    operations = [
        migrations.RunPython(validate_existing_statement_periods, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="billingstatement",
            constraint=models.UniqueConstraint(
                fields=("customer", "period_start", "period_end"),
                name="uniq_customer_billing_statement_period",
            ),
        ),
        migrations.AddConstraint(
            model_name="billingstatement",
            constraint=models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F("period_start")),
                name="billing_statement_period_valid",
            ),
        ),
    ]
