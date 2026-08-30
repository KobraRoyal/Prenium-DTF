"""Purge seed recette data without re-seeding. Run via manage.py shell on NAS."""

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.b2b_order_projects.models import B2BOrderProject
from apps.catalog.models import CatalogService
from apps.customers.models import Customer
from apps.gang_sheets.models import GangSheet
from apps.orders.models import Order
from apps.uploads.models import Asset

SEED_EMAILS = [
    "admin@prenium.local",
    "staff.ops@prenium.local",
    "staff.limited@prenium.local",
    "client.a.owner@prenium.local",
    "client.a.member@prenium.local",
    "client.b.owner@prenium.local",
    "client.cash.owner@prenium.local",
    "hybrid.ops.client@prenium.local",
]


@transaction.atomic
def purge_seed_data() -> dict[str, int]:
    seed_customers = Customer.objects.filter(name__startswith="Seed ")
    counts = {
        "customers": seed_customers.count(),
        "b2b_projects": 0,
        "orders": 0,
        "gang_sheets": 0,
        "assets": 0,
        "catalog_services": 0,
        "users": 0,
    }

    counts["b2b_projects"] = B2BOrderProject.objects.filter(customer__in=seed_customers).count()
    B2BOrderProject.objects.filter(customer__in=seed_customers).delete()

    counts["gang_sheets"] = GangSheet.objects.filter(customer__in=seed_customers).count()
    GangSheet.objects.filter(customer__in=seed_customers).delete()

    counts["orders"] = Order.objects.filter(customer__in=seed_customers).count()
    Order.objects.filter(customer__in=seed_customers).delete()

    counts["assets"] = Asset.objects.filter(customer__in=seed_customers).count()
    Asset.objects.filter(customer__in=seed_customers).delete()

    seed_customers.delete()

    counts["catalog_services"] = CatalogService.objects.filter(code__startswith="seed-").count()
    CatalogService.objects.filter(code__startswith="seed-").delete()

    _, deleted_users = get_user_model().objects.filter(email__in=SEED_EMAILS).delete()
    counts["users"] = deleted_users

    return counts


result = purge_seed_data()
print("SEED_PURGED", result)
