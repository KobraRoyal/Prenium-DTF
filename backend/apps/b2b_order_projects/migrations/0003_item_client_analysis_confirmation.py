import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("b2b_order_projects", "0002_b2borderprojectitem_asset"),
        ("uploads", "0012_assetversion_auto_size_requested"),
    ]

    operations = [
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="client_confirmed_asset_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="uploads.assetversion",
            ),
        ),
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="client_confirmed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="b2borderprojectitem",
            name="client_confirmed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="confirmed_b2b_order_project_items",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name="b2borderprojectitem",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        client_confirmed_asset_version__isnull=True,
                        client_confirmed_at__isnull=True,
                    )
                    | models.Q(
                        client_confirmed_asset_version__isnull=False,
                        client_confirmed_at__isnull=False,
                    )
                ),
                name="b2b_item_confirmation_pair",
            ),
        ),
    ]
