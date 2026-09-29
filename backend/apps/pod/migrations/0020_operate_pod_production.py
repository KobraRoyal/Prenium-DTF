from django.conf import settings
from django.db import migrations


def grant_production_to_current_catalog_managers(apps, schema_editor):
    ContentType = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")
    Group = apps.get_model("auth", "Group")
    content_type, _created = ContentType.objects.get_or_create(
        app_label="pod",
        model="printtechnique",
    )
    production, _created = Permission.objects.get_or_create(
        codename="operate_pod_production",
        content_type=content_type,
        defaults={"name": "Can operate POD production floor"},
    )
    catalog = Permission.objects.filter(
        codename="manage_pod_catalog",
        content_type=content_type,
    ).first()
    if catalog is None:
        return
    for user in User.objects.filter(user_permissions=catalog).iterator():
        user.user_permissions.add(production)
    for group in Group.objects.filter(permissions=catalog).iterator():
        group.permissions.add(production)


def remove_production_permission(apps, schema_editor):
    Permission = apps.get_model("auth", "Permission")
    Permission.objects.filter(
        codename="operate_pod_production",
        content_type__app_label="pod",
        content_type__model="printtechnique",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0019_pod_drive_hd_source"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="printtechnique",
            options={
                "ordering": ("display_order", "name"),
                "permissions": [
                    ("access_pod_atelier", "Can access POD atelier catalog and warehouse"),
                    ("manage_pod_catalog", "Can manage POD techniques and blanks"),
                    ("operate_pod_production", "Can operate POD production floor"),
                ],
            },
        ),
        migrations.RunPython(
            grant_production_to_current_catalog_managers,
            remove_production_permission,
        ),
    ]
