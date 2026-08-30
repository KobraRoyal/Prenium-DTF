from decimal import Decimal

import pytest
from apps.catalog.models import CatalogService
from apps.catalog.services.default_catalog import DefaultCatalogService
from django.apps import apps as django_apps


@pytest.mark.django_db
def test_default_catalog_service_bootstrap_creates_required_services():
    CatalogService.objects.filter(code__in=["seed-dtf-meter", "seed-file-prep"]).delete()

    created = DefaultCatalogService().ensure_default_services()

    assert len(created) == 2
    dtf = CatalogService.objects.get(code="seed-dtf-meter")
    prep = CatalogService.objects.get(code="seed-file-prep")
    assert dtf.base_price == Decimal("25.00")
    assert prep.base_price == Decimal("10.00")
    assert dtf.is_active is True
    assert prep.is_active is True

    assert DefaultCatalogService().ensure_default_services() == []


@pytest.mark.django_db
def test_catalog_migration_seed_function_bootstraps_services():
    from importlib import import_module

    migration = import_module("apps.catalog.migrations.0002_seed_default_catalog_services")
    CatalogService.objects.filter(code__in=["seed-dtf-meter", "seed-file-prep"]).delete()

    migration.seed_default_catalog_services(django_apps, None)

    assert CatalogService.objects.filter(code="seed-dtf-meter", is_active=True).exists()
    assert CatalogService.objects.filter(code="seed-file-prep", is_active=True).exists()
