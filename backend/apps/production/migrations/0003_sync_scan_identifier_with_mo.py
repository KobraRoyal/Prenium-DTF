# Generated manually — aligne scan_identifier sur la référence OF (GPAO).

from django.db import migrations


def sync_scan_with_manufacturing_order(apps, schema_editor):
    ProductionJob = apps.get_model("production", "ProductionJob")
    for job in ProductionJob.objects.all().iterator():
        if job.scan_identifier != job.manufacturing_order_number:
            job.scan_identifier = job.manufacturing_order_number
            job.save(update_fields=["scan_identifier"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0002_productionjobscanlog_alter_productionjob_options_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_scan_with_manufacturing_order, noop_reverse),
    ]
