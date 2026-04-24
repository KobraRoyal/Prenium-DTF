# Suivi paiement facture (virement) + rétrocompatibilité PayPal.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import F


def backfill_invoice_paid_at_from_paypal(apps, schema_editor):
    Invoice = apps.get_model("billing", "Invoice")
    Invoice.objects.filter(
        payment__isnull=False,
        payment__status="captured",
        paid_at__isnull=True,
    ).exclude(issued_at__isnull=True).update(paid_at=F("issued_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_b2b_deferred_billing"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="paid_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Règlement reçu : date de confirmation (virement ou équivalent). Les factures PayPal sont soldées à l’émission.",
                null=True,
                verbose_name="Payée le",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="paid_recorded_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoices_marked_paid",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Paiement enregistré par",
            ),
        ),
        migrations.AddIndex(
            model_name="invoice",
            index=models.Index(fields=["paid_at"], name="billing_inv_paid_at_8a1b2c_idx"),
        ),
        migrations.AlterModelOptions(
            name="invoice",
            options={
                "ordering": ("-issued_at", "-created_at"),
                "permissions": (
                    ("mark_invoice_paid", "Marquer une facture comme payée (virement)"),
                ),
            },
        ),
        migrations.RunPython(backfill_invoice_paid_at_from_paypal, migrations.RunPython.noop),
    ]
