from django.db import migrations

OLD_NOTE_PREFIX = "Préparation "
NEW_NOTE_PREFIX = "Gang Sheet "


def rename_preparation_note_prefix(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.filter(customer_note__contains=OLD_NOTE_PREFIX).iterator():
        order.customer_note = order.customer_note.replace(OLD_NOTE_PREFIX, NEW_NOTE_PREFIX)
        order.save(update_fields=["customer_note", "updated_at"])


def revert_preparation_note_prefix(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.filter(customer_note__contains=NEW_NOTE_PREFIX).iterator():
        order.customer_note = order.customer_note.replace(NEW_NOTE_PREFIX, OLD_NOTE_PREFIX)
        order.save(update_fields=["customer_note", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0006_rename_project_number_prefix_gang_sheet"),
        ("orders", "0007_monthly_volume_discount_snapshots"),
    ]

    operations = [
        migrations.RunPython(rename_preparation_note_prefix, revert_preparation_note_prefix),
    ]
