# Generated manually — services catalogue par défaut (DTF + préparation fichier).

from decimal import Decimal

from django.db import migrations


def seed_default_catalog_services(apps, schema_editor):
    CatalogService = apps.get_model("catalog", "CatalogService")
    defaults = (
        {
            "code": "seed-dtf-meter",
            "name": "DTF au mètre",
            "description": "Impression DTF — tarif catalogue au m².",
            "service_type": "dtf_transfer",
            "unit": "linear_meter",
            "base_price": Decimal("25.00"),
            "display_order": 10,
        },
        {
            "code": "seed-file-prep",
            "name": "Préparation fichier",
            "description": "Traitement et préparation fichier — forfait par fichier.",
            "service_type": "file_preparation",
            "unit": "fixed",
            "base_price": Decimal("10.00"),
            "display_order": 20,
        },
    )
    for payload in defaults:
        CatalogService.objects.get_or_create(
            code=payload["code"],
            defaults={
                **payload,
                "currency": "EUR",
                "is_active": True,
            },
        )


def unseed_default_catalog_services(apps, schema_editor):
    CatalogService = apps.get_model("catalog", "CatalogService")
    CatalogService.objects.filter(code__in=["seed-dtf-meter", "seed-file-prep"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_catalog_services, unseed_default_catalog_services),
    ]
