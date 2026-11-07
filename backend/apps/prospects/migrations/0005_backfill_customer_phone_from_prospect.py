from django.db import migrations


def forwards(apps, schema_editor):
    ProspectProfile = apps.get_model("prospects", "ProspectProfile")
    for profile in ProspectProfile.objects.exclude(customer_id=None).exclude(phone=""):
        customer = profile.customer
        if customer is None:
            continue
        if (customer.phone or "").strip():
            continue
        customer.phone = str(profile.phone).strip()[:32]
        customer.save(update_fields=["phone"])


def backwards(apps, schema_editor):
    # Irreversible backfill: leave customer phones as-is.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("customers", "0019_customer_phone"),
        ("prospects", "0004_prospectprofile_billing_address_line1_and_more"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
