from django.db import migrations, models

FINANCIAL_STATUSES = ("captured", "captured_review")


def validate_existing_payment_settlements(apps, schema_editor):
    payment_model = apps.get_model("billing", "Payment")
    duplicate_orders = (
        payment_model.objects.filter(status__in=FINANCIAL_STATUSES)
        .values("order_id")
        .annotate(count=models.Count("id"))
        .filter(count__gt=1)
    )
    if duplicate_orders.exists():
        raise RuntimeError(
            "Migration interrompue : plusieurs captures financières existent pour une "
            "même commande. Réconciliez-les avec les providers avant de relancer."
        )

    ambiguous_rows = payment_model.objects.filter(
        models.Q(paypal_capture_id__gt="") | models.Q(stripe_payment_intent_id__gt=""),
        status__in=("failed", "cancelled"),
    )
    if ambiguous_rows.exists():
        raise RuntimeError(
            "Migration interrompue : des paiements annulés ou échoués possèdent un "
            "identifiant de capture. Réconciliez-les avant de relancer."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0008_billing_statement_snapshots"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("approved", "Approved"),
                    ("captured", "Captured"),
                    ("captured_review", "Capture à vérifier"),
                    ("failed", "Failed"),
                    ("cancelled", "Cancelled"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            validate_existing_payment_settlements,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="payment",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=FINANCIAL_STATUSES),
                fields=("order",),
                name="uniq_financial_settlement_per_order",
            ),
        ),
    ]
