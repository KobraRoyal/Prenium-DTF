from django.db import migrations

OLD_PREFIX = "DTF-B2B-"
NEW_PREFIX = "GANG-SHEET-"


def rename_project_number_prefix(apps, schema_editor):
    B2BOrderProject = apps.get_model("b2b_order_projects", "B2BOrderProject")
    Order = apps.get_model("orders", "Order")

    for project in B2BOrderProject.objects.filter(project_number__startswith=OLD_PREFIX).iterator():
        project.project_number = NEW_PREFIX + project.project_number[len(OLD_PREFIX) :]
        project.save(update_fields=["project_number", "updated_at"])

    for order in Order.objects.filter(customer_note__contains=OLD_PREFIX).iterator():
        order.customer_note = order.customer_note.replace(OLD_PREFIX, NEW_PREFIX)
        order.save(update_fields=["customer_note", "updated_at"])


def revert_project_number_prefix(apps, schema_editor):
    B2BOrderProject = apps.get_model("b2b_order_projects", "B2BOrderProject")
    Order = apps.get_model("orders", "Order")

    for project in B2BOrderProject.objects.filter(project_number__startswith=NEW_PREFIX).iterator():
        project.project_number = OLD_PREFIX + project.project_number[len(NEW_PREFIX) :]
        project.save(update_fields=["project_number", "updated_at"])

    for order in Order.objects.filter(customer_note__contains=NEW_PREFIX).iterator():
        order.customer_note = order.customer_note.replace(NEW_PREFIX, OLD_PREFIX)
        order.save(update_fields=["customer_note", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0005_b2b_item_crop"),
        ("orders", "0007_monthly_volume_discount_snapshots"),
    ]

    operations = [
        migrations.RunPython(rename_project_number_prefix, revert_project_number_prefix),
    ]
