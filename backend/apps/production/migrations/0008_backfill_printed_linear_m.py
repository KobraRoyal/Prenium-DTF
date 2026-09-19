from django.db import migrations


def backfill_printed_linear_m(apps, schema_editor):
    """Remplit les snapshots nuls créés avant le code de confirmation métrage."""
    ProductionPrintRecord = apps.get_model("production", "ProductionPrintRecord")
    records = ProductionPrintRecord.objects.filter(printed_linear_m__isnull=True).select_related(
        "production_job__order"
    )
    updates = []
    for record in records.iterator(chunk_size=200):
        meterage = record.production_job.order.meterage_override_linear_m
        if meterage is None:
            continue
        record.printed_linear_m = meterage
        updates.append(record)
        if len(updates) >= 200:
            ProductionPrintRecord.objects.bulk_update(updates, ["printed_linear_m"])
            updates = []
    if updates:
        ProductionPrintRecord.objects.bulk_update(updates, ["printed_linear_m"])


def noop_reverse(apps, schema_editor):
    """Conserve les métrages déjà figés ; pas de retour arrière destructif."""


class Migration(migrations.Migration):

    dependencies = [
        ("production", "0007_productionprintrecord_printed_linear_m"),
        ("orders", "0003_order_meterage_override_linear_m"),
    ]

    operations = [
        migrations.RunPython(backfill_printed_linear_m, noop_reverse),
    ]
