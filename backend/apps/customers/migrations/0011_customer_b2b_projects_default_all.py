from django.db import migrations, models


def enable_projects_for_all_customers(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    Customer.objects.filter(b2b_order_projects_enabled=False).update(
        b2b_order_projects_enabled=True
    )


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0010_customer_manage_pricing_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="customer",
            name="b2b_order_projects_enabled",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Champ historique. Le parcours projet est le flux standard pour tous les "
                    "clients actifs lorsque B2B_DTF_ORDER_PROJECT_ENABLED est actif."
                ),
                verbose_name="Projets de commande B2B activés (historique)",
            ),
        ),
        migrations.RunPython(
            enable_projects_for_all_customers,
            migrations.RunPython.noop,
        ),
    ]
