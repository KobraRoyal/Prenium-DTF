from __future__ import annotations

from decimal import Decimal

from apps.catalog.models import CatalogService

DEFAULT_CATALOG_SERVICE_SEED = (
    {
        "code": "seed-dtf-meter",
        "name": "DTF au mètre",
        "description": "Impression DTF — tarif catalogue au m².",
        "service_type": CatalogService.ServiceType.DTF_TRANSFER,
        "unit": CatalogService.Unit.LINEAR_METER,
        "base_price": Decimal("25.00"),
        "display_order": 10,
    },
    {
        "code": "seed-file-prep",
        "name": "Préparation fichier",
        "description": "Traitement et préparation fichier — forfait par fichier.",
        "service_type": CatalogService.ServiceType.FILE_PREPARATION,
        "unit": CatalogService.Unit.FIXED,
        "base_price": Decimal("10.00"),
        "display_order": 20,
    },
)


class DefaultCatalogService:
    """Bootstrap idempotent des services catalogue requis pour la tarification."""

    def ensure_default_services(self) -> list[CatalogService]:
        created: list[CatalogService] = []
        for payload in DEFAULT_CATALOG_SERVICE_SEED:
            service, was_created = CatalogService.objects.get_or_create(
                code=payload["code"],
                defaults={
                    "name": payload["name"],
                    "description": payload["description"],
                    "service_type": payload["service_type"],
                    "unit": payload["unit"],
                    "base_price": payload["base_price"],
                    "currency": "EUR",
                    "display_order": payload["display_order"],
                    "is_active": True,
                },
            )
            if was_created:
                created.append(service)
        return created
