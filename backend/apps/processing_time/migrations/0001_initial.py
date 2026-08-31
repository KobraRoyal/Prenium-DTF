import uuid
from decimal import Decimal

import django.core.validators
from django.db import migrations, models


def seed_processing_time_options(apps, schema_editor):
    ProcessingTimeOption = apps.get_model("processing_time", "ProcessingTimeOption")
    defaults = (
        {
            "code": "standard",
            "name": "Standard",
            "eta_label": "Imprimé et expédié dans 3 jours",
            "disclaimer": "Hors weekend et jour férié",
            "business_days": 3,
            "markup_percent": Decimal("0.00"),
            "flat_fee_eur": Decimal("0.00"),
            "is_default": True,
            "display_order": 10,
        },
        {
            "code": "fast",
            "name": "Rapide",
            "eta_label": "Imprimé et expédié dans 2 jours",
            "disclaimer": "Hors weekend et jour férié",
            "business_days": 2,
            "markup_percent": Decimal("20.00"),
            "flat_fee_eur": Decimal("0.00"),
            "is_default": False,
            "display_order": 20,
        },
        {
            "code": "express",
            "name": "Express",
            "eta_label": "Imprimé et expédié demain",
            "disclaimer": "Hors weekend et jour férié",
            "business_days": 0,
            "markup_percent": Decimal("40.00"),
            "flat_fee_eur": Decimal("7.00"),
            "is_default": False,
            "display_order": 30,
        },
    )
    for payload in defaults:
        ProcessingTimeOption.objects.get_or_create(
            code=payload["code"],
            defaults={**payload, "is_active": True},
        )


def unseed_processing_time_options(apps, schema_editor):
    ProcessingTimeOption = apps.get_model("processing_time", "ProcessingTimeOption")
    ProcessingTimeOption.objects.filter(code__in=["standard", "fast", "express"]).delete()


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ProcessingTimeOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("public_id", models.UUIDField(db_index=True, default=uuid.uuid4, editable=False, unique=True)),
                ("code", models.SlugField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "eta_label",
                    models.CharField(
                        help_text="Libellé délai affiché au client (ex. « Imprimé et expédié dans 3 jours »).",
                        max_length=255,
                    ),
                ),
                (
                    "disclaimer",
                    models.CharField(
                        default="Hors weekend et jour férié",
                        help_text="Mention légale affichée entre guillemets après le délai.",
                        max_length=255,
                    ),
                ),
                (
                    "business_days",
                    models.PositiveSmallIntegerField(
                        default=3,
                        help_text="Délai métier en jours ouvrés (0 = demain / express).",
                        validators=[django.core.validators.MinValueValidator(0)],
                    ),
                ),
                (
                    "markup_percent",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Majoration en % appliquée au montant DTF (planche).",
                        max_digits=5,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "flat_fee_eur",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        help_text="Forfait HT additionnel (ex. express +7 €).",
                        max_digits=10,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "is_default",
                    models.BooleanField(
                        default=False,
                        help_text="Option présélectionnée au checkout si aucun choix client.",
                    ),
                ),
                ("display_order", models.PositiveIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ("display_order", "name"),
            },
        ),
        migrations.AddIndex(
            model_name="processingtimeoption",
            index=models.Index(fields=["is_active", "display_order"], name="proc_time_is_act_disp_idx"),
        ),
        migrations.RunPython(seed_processing_time_options, unseed_processing_time_options),
    ]
