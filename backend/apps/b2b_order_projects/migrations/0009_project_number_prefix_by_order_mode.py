from django.db import migrations

GANG_SHEET_PREFIX = "GANG-SHEET-"
FILE_ORDER_PREFIX = "CMD-"
READY_GANG_SHEET = "ready_gang_sheet"


def rename_non_gang_sheet_prefixes(apps, schema_editor):
    B2BOrderProject = apps.get_model("b2b_order_projects", "B2BOrderProject")
    Order = apps.get_model("orders", "Order")

    projects = B2BOrderProject.objects.exclude(order_mode=READY_GANG_SHEET).filter(
        project_number__startswith=GANG_SHEET_PREFIX
    )
    for project in projects.iterator():
        old_number = project.project_number
        new_number = FILE_ORDER_PREFIX + old_number[len(GANG_SHEET_PREFIX) :]
        project.project_number = new_number
        project.save(update_fields=["project_number", "updated_at"])
        for order in Order.objects.filter(customer_note__contains=old_number).iterator():
            order.customer_note = order.customer_note.replace(old_number, new_number)
            # Also drop misleading "Gang Sheet " label for file orders when present.
            order.customer_note = order.customer_note.replace(
                f"Gang Sheet {new_number}", f"Commande {new_number}"
            )
            order.save(update_fields=["customer_note", "updated_at"])


def revert_non_gang_sheet_prefixes(apps, schema_editor):
    B2BOrderProject = apps.get_model("b2b_order_projects", "B2BOrderProject")
    Order = apps.get_model("orders", "Order")

    projects = B2BOrderProject.objects.exclude(order_mode=READY_GANG_SHEET).filter(
        project_number__startswith=FILE_ORDER_PREFIX
    )
    for project in projects.iterator():
        old_number = project.project_number
        new_number = GANG_SHEET_PREFIX + old_number[len(FILE_ORDER_PREFIX) :]
        project.project_number = new_number
        project.save(update_fields=["project_number", "updated_at"])
        for order in Order.objects.filter(customer_note__contains=old_number).iterator():
            order.customer_note = order.customer_note.replace(old_number, new_number)
            order.customer_note = order.customer_note.replace(
                f"Commande {new_number}", f"Gang Sheet {new_number}"
            )
            order.save(update_fields=["customer_note", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("b2b_order_projects", "0008_alter_b2borderprojectnumbersequence_options"),
        ("orders", "0008_billing_statement_freeze"),
    ]

    operations = [
        migrations.RunPython(rename_non_gang_sheet_prefixes, revert_non_gang_sheet_prefixes),
    ]
