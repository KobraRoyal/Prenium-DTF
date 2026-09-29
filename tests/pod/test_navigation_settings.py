from __future__ import annotations

import uuid

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.inventory.models import StorageLocation, Warehouse, WarehouseZone
from apps.pod.models import (
    Blank,
    IdsVariantConfig,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.settings_overview import PodSettingsOverviewService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _staff_user(*, email: str, permissions: tuple[str, ...]):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        *(Permission.objects.get(codename=codename) for codename in permissions),
    )
    return user


def _staff_client(*, email: str, permissions: tuple[str, ...]) -> Client:
    _staff_user(email=email, permissions=permissions)
    client = Client()
    assert client.login(email=email, password="pass")
    return client


def _client_user_client() -> Client:
    user = get_user_model().objects.create_user(
        email="pod-settings-client@example.com",
        password="pass",
    )
    CustomerMembership.objects.create(
        customer=Customer.objects.create(name="Client réglages"),
        user=user,
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    return client


def _catalog_urls() -> tuple[str, ...]:
    missing_id = uuid.uuid4()
    return (
        reverse("portal:staff-pod-techniques"),
        reverse("portal:staff-pod-blanks"),
        reverse(
            "portal:staff-pod-blank-detail",
            kwargs={"blank_public_id": missing_id},
        ),
        reverse(
            "portal:staff-pod-blank-photo",
            kwargs={"blank_public_id": missing_id},
        ),
        reverse(
            "portal:staff-pod-blank-variant-photo",
            kwargs={"blank_public_id": missing_id, "variant_public_id": uuid.uuid4()},
        ),
        reverse("portal:staff-pod-catalog"),
        reverse(
            "portal:staff-pod-catalog-product",
            kwargs={"product_public_id": missing_id},
        ),
        reverse(
            "portal:staff-pod-variant-config",
            kwargs={"variant_public_id": missing_id},
        ),
        reverse("portal:staff-pod-shops"),
    )


def _catalog_mutation_urls() -> tuple[str, ...]:
    missing_id = uuid.uuid4()
    return (
        reverse("portal:staff-pod-techniques"),
        reverse("portal:staff-pod-blanks"),
        reverse(
            "portal:staff-pod-blank-detail",
            kwargs={"blank_public_id": missing_id},
        ),
        reverse(
            "portal:staff-pod-variant-config",
            kwargs={"variant_public_id": missing_id},
        ),
        reverse("portal:staff-pod-shops"),
    )


def test_operator_is_denied_settings_and_direct_catalog_configuration_urls():
    client = _staff_client(
        email="pod-settings-operator@example.com",
        permissions=("access_pod_atelier",),
    )

    for url in (reverse("portal:staff-pod-settings"), *_catalog_urls()):
        assert client.get(url).status_code == 403
    for url in _catalog_mutation_urls():
        assert client.post(url, {}).status_code == 403

    assert AuditLogEntry.objects.filter(
        action="pod.atelier.permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_catalog_manager_can_open_catalog_and_settings_but_not_warehouse():
    client = _staff_client(
        email="pod-settings-catalog@example.com",
        permissions=("access_pod_atelier", "manage_pod_catalog"),
    )

    settings_response = client.get(reverse("portal:staff-pod-settings"))
    assert settings_response.status_code == 200
    assert settings_response.context["can_manage_catalog"] is True
    assert settings_response.context["can_manage_warehouse"] is False
    assert client.get(reverse("portal:staff-pod-catalog")).status_code == 200
    assert client.get(reverse("portal:staff-pod-warehouse")).status_code == 403
    assert client.post(reverse("portal:staff-pod-warehouse"), {}).status_code == 403
    assert (
        client.get(
            reverse(
                "portal:staff-pod-location-detail",
                kwargs={"location_public_id": uuid.uuid4()},
            )
        ).status_code
        == 403
    )


def test_warehouse_manager_can_open_warehouse_and_settings_but_not_catalog():
    client = _staff_client(
        email="pod-settings-warehouse@example.com",
        permissions=("access_pod_atelier", "manage_warehouse"),
    )

    settings_response = client.get(reverse("portal:staff-pod-settings"))
    assert settings_response.status_code == 200
    assert settings_response.context["can_manage_catalog"] is False
    assert settings_response.context["can_manage_warehouse"] is True
    assert settings_response.context["settings_overview"] == {
        "disconnected_shops_count": 0,
        "variants_needing_mapping_count": 0,
        "supports_without_variants_count": 0,
        "locations_count": 0,
    }
    assert client.get(reverse("portal:staff-pod-warehouse")).status_code == 200
    assert client.get(reverse("portal:staff-pod-catalog")).status_code == 403
    assert client.get(reverse("portal:staff-pod-shops")).status_code == 403
    assert client.post(reverse("portal:staff-pod-shops"), {}).status_code == 403


def test_settings_get_is_read_only_and_returns_real_aggregate_counts():
    client = _staff_client(
        email="pod-settings-summary@example.com",
        permissions=(
            "access_pod_atelier",
            "manage_pod_catalog",
            "manage_warehouse",
        ),
    )
    disconnected = ShopifyStore.objects.create(
        slug="settings-disconnected",
        name="Boutique à reconnecter",
        shop_domain="settings-disconnected.myshopify.com",
        webhook_secret="must-not-leak",
    )
    connected = ShopifyStore.objects.create(
        slug="settings-connected",
        name="Boutique connectée",
        shop_domain="settings-connected.myshopify.com",
        access_token_encrypted="ciphertext-must-not-leak",
    )
    product = ShopifyProduct.objects.create(
        store=connected,
        external_id="settings-product",
        title="Produit à mapper",
    )
    ShopifyVariant.objects.create(
        product=product,
        external_id="settings-variant",
        title="M",
    )
    incomplete_stock_variant = ShopifyVariant.objects.create(
        product=product,
        external_id="settings-stock-variant",
        title="L",
    )
    IdsVariantConfig.objects.create(
        variant=incomplete_stock_variant,
        mode=IdsVariantConfig.Mode.ON_STOCK,
        finished_sku="",
    )
    Blank.objects.create(sku="SETTINGS-NO-VARIANT", name="Support incomplet")
    warehouse = Warehouse.objects.create(code="settings", name="Entrepôt réglages")
    zone = WarehouseZone.objects.create(
        warehouse=warehouse,
        code="settings-zone",
        name="Zone réglages",
        kind=WarehouseZone.Kind.BLANKS,
    )
    StorageLocation.objects.create(zone=zone, code="SETTINGS-01")
    before = {
        "stores": ShopifyStore.objects.count(),
        "variants": ShopifyVariant.objects.count(),
        "blanks": Blank.objects.count(),
        "locations": StorageLocation.objects.count(),
    }

    response = client.get(reverse("portal:staff-pod-settings"))

    assert response.status_code == 200
    assert response.context["settings_overview"] == {
        "disconnected_shops_count": 1,
        "variants_needing_mapping_count": 2,
        "supports_without_variants_count": 1,
        "locations_count": 1,
    }
    assert {
        "stores": ShopifyStore.objects.count(),
        "variants": ShopifyVariant.objects.count(),
        "blanks": Blank.objects.count(),
        "locations": StorageLocation.objects.count(),
    } == before
    assert disconnected.webhook_secret not in response.content.decode()
    assert connected.access_token_encrypted not in response.content.decode()


def test_warehouse_only_overview_skips_all_catalog_queries(django_assert_num_queries):
    actor = _staff_user(
        email="pod-settings-warehouse-queries@example.com",
        permissions=("access_pod_atelier", "manage_warehouse"),
    )
    actor.get_all_permissions()
    ShopifyStore.objects.create(
        slug="hidden-from-warehouse",
        name="Boutique masquée",
        shop_domain="hidden-from-warehouse.myshopify.com",
    )

    with django_assert_num_queries(1):
        overview = PodSettingsOverviewService().build(actor=actor)

    assert overview == {
        "disconnected_shops_count": 0,
        "variants_needing_mapping_count": 0,
        "supports_without_variants_count": 0,
        "locations_count": 0,
    }


def test_anonymous_and_client_users_cannot_open_settings():
    url = reverse("portal:staff-pod-settings")
    assert Client().get(url).status_code == 302
    assert _client_user_client().get(url).status_code == 403
