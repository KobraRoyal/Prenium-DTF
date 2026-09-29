import uuid

from django.db import migrations, models

MARKING_ZONES = (
    ("front", "Devant"),
    ("back", "Dos"),
    ("left_chest", "Cœur"),
    ("right_chest", "Poitrine droite"),
    ("sleeve_left", "Manche gauche"),
    ("sleeve_right", "Manche droite"),
    ("collar", "Col"),
    ("other", "Autre"),
)


def seed_and_backfill_marking_options(apps, schema_editor):
    Blank = apps.get_model("pod", "Blank")
    Capability = apps.get_model("pod", "BlankPlacementCapability")
    MarkingZone = apps.get_model("pod", "MarkingZone")

    zones_by_code = {}
    for display_order, (code, name) in enumerate(MARKING_ZONES):
        zone, _created = MarkingZone.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "display_order": display_order,
                "is_active": True,
            },
        )
        zones_by_code[code] = zone

    for blank in Blank.objects.all().iterator():
        capabilities = Capability.objects.filter(blank=blank, is_active=True)
        zone_ids = {
            zones_by_code[placement].pk
            for placement in capabilities.values_list("placement", flat=True)
            if placement in zones_by_code
        }
        technique_ids = set(capabilities.values_list("technique_id", flat=True))
        blank.allowed_zones.add(*zone_ids)
        blank.allowed_techniques.add(*technique_ids)
        blank.marking_options_configured = True
        blank.save(update_fields=["marking_options_configured", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("pod", "0017_pod_quality_check"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarkingZone",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "public_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        unique=True,
                    ),
                ),
                ("code", models.SlugField(editable=False, max_length=32, unique=True)),
                ("name", models.CharField(max_length=120)),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ("display_order", "name"),
                "indexes": [
                    models.Index(
                        fields=["is_active", "display_order"],
                        name="pod_marking_active_order_idx",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="blank",
            name="allowed_techniques",
            field=models.ManyToManyField(
                blank=True,
                related_name="allowed_blanks",
                to="pod.printtechnique",
            ),
        ),
        migrations.AddField(
            model_name="blank",
            name="allowed_zones",
            field=models.ManyToManyField(
                blank=True,
                related_name="blanks",
                to="pod.markingzone",
            ),
        ),
        migrations.AddField(
            model_name="blank",
            name="marking_options_configured",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(seed_and_backfill_marking_options, migrations.RunPython.noop),
    ]
