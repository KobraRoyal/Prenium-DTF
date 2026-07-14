from django.db import migrations, models


def merge_legacy_b2b_template(apps, schema_editor):
    email_template = apps.get_model("notifications", "EmailTemplate")
    for legacy in email_template.objects.filter(event="b2b_order_submitted"):
        created_override_exists = email_template.objects.filter(
            event="order_created",
            audience=legacy.audience,
        ).exists()
        if created_override_exists:
            legacy.delete()
            continue
        legacy.event = "order_created"
        legacy.save(update_fields=["event"])


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0002_alter_emailtemplate_event"),
    ]

    operations = [
        migrations.RunPython(merge_legacy_b2b_template, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="emailtemplate",
            name="event",
            field=models.CharField(
                choices=[
                    ("order_created", "Commande créée"),
                    ("payment_captured", "Paiement confirmé"),
                    ("order_processing", "Commande en traitement"),
                    ("order_ready_to_ship", "Commande traitée"),
                    ("order_shipped", "Commande expédiée"),
                    ("order_priced", "Commande tarifée"),
                    ("file_correction_requested", "Correction fichier demandée"),
                ],
                max_length=32,
                verbose_name="Événement",
            ),
        ),
    ]
