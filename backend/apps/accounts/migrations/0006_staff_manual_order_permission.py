from django.db import migrations


def grant_manual_order_creation(apps, schema_editor):
    alias = schema_editor.connection.alias
    content_type, _ = (
        apps.get_model("contenttypes", "ContentType")
        .objects.using(alias)
        .get_or_create(app_label="orders", model="order")
    )
    permission, _ = (
        apps.get_model("auth", "Permission")
        .objects.using(alias)
        .get_or_create(
            content_type_id=content_type.pk,
            codename="add_order",
            defaults={"name": "Can add order"},
        )
    )
    memberships = (
        apps.get_model("accounts", "StaffMembership")
        .objects.using(alias)
        .filter(
            is_active=True, role__in=["owner", "admin"], user__is_active=True, user__is_staff=True
        )
    )
    through = apps.get_model("accounts", "User").user_permissions.through
    for user_id in memberships.values_list("user_id", flat=True):
        through.objects.using(alias).get_or_create(user_id=user_id, permission_id=permission.pk)


class Migration(migrations.Migration):
    dependencies = [
        (
            "accounts",
            "0005_rename_accounts_st_status_8d2f1a_idx_accounts_st_status_fa0977_idx_and_more",
        ),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]
    operations = [migrations.RunPython(grant_manual_order_creation, migrations.RunPython.noop)]
