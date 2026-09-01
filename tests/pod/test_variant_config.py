from __future__ import annotations

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.pod.models import (
    BlankPlacementCapability,
    IdsVariantConfig,
    PodRecipeTemplate,
    PodRecipeTemplateSlot,
    PrintTechnique,
    ShopifyVariant,
)
from apps.pod.services import (
    BlankCatalogService,
    PrintTechniqueService,
    ShopifyCatalogService,
    VariantConfigService,
)
from apps.pod.services.variant_config import CONFIG_STATUS_POD
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

catalog = BlankCatalogService()
techniques = PrintTechniqueService()
shopify = ShopifyCatalogService()
variant_config = VariantConfigService()


def grant(user, *codenames):
    user.user_permissions.add(
        *(Permission.objects.get(codename=codename) for codename in codenames)
    )


def staff_client(*, email: str, permissions: tuple[str, ...]):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    grant(user, "access_staff_portal", *permissions)
    client = Client()
    assert client.login(email=email, password="pass")
    return user, client


def pod_fixture(*, actor):
    techniques.ensure_dtf_technique(actor=actor)
    dtf = PrintTechnique.objects.get(code="dtf")
    blank = catalog.create_blank(
        actor=actor,
        source="test",
        data={"sku": "TEE-POD", "name": "T-shirt test"},
    )
    blank_variant = catalog.create_variant(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={"sku": "TEE-POD-M", "size_label": "M", "color_name": "Noir"},
    )
    catalog.add_capability(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={
            "placement": BlankPlacementCapability.Placement.FRONT,
            "technique_public_id": str(dtf.public_id),
            "is_required": True,
        },
    )
    catalog.add_capability(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={
            "placement": BlankPlacementCapability.Placement.LEFT_CHEST,
            "technique_public_id": str(dtf.public_id),
            "is_required": False,
        },
    )
    product = shopify.ensure_demo_catalog(actor=actor)
    variant = product.variants.get(sku="TEE-BLK-M")
    return dtf, blank, blank_variant, variant


MANAGE = ("access_pod_atelier", "manage_pod_catalog")
VIEW = ("access_pod_atelier",)


def test_catalogue_lists_variants_with_needs_config_badge():
    actor, client = staff_client(email="staff-d1-list@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    response = client.get(reverse("portal:staff-pod-catalog"))
    assert response.status_code == 200
    assert b"needs_config" in response.content or b"unmanaged" in response.content
    assert variant.sku.encode() in response.content


def test_variant_drawer_saves_pod_mix_and_becomes_ready():
    actor, client = staff_client(email="staff-d1-save@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    drawer_url = reverse(
        "portal:staff-pod-variant-config",
        kwargs={"variant_public_id": variant.public_id},
    )
    get_response = client.get(drawer_url)
    assert get_response.status_code == 200
    assert b"Config variante" in get_response.content
    post_response = client.post(
        drawer_url,
        {
            "intent": "save",
            "mode": "pod",
            "blank_variant_public_id": str(blank_variant.public_id),
            "slot_placement": [
                BlankPlacementCapability.Placement.FRONT,
                BlankPlacementCapability.Placement.LEFT_CHEST,
            ],
            "slot_technique_public_id": [str(dtf.public_id), str(dtf.public_id)],
            "slot_print_reference": ["front_hd.png", "heart_hd.png"],
            "slot_required_0": "1",
            "slot_enabled": [
                f"{BlankPlacementCapability.Placement.FRONT}:{dtf.public_id}",
                f"{BlankPlacementCapability.Placement.LEFT_CHEST}:{dtf.public_id}",
            ],
        },
        HTTP_HX_REQUEST="true",
    )
    assert post_response.status_code == 200
    config = ShopifyVariant.objects.get(pk=variant.pk).ids_config
    assert variant_config.configuration_status(config) == CONFIG_STATUS_POD
    assert config.recipe.slots.count() == 2
    assert AuditLogEntry.objects.filter(action="pod.variant_config.saved").exists()


def test_pod_without_required_print_reference_stays_needs_config():
    actor, _client = staff_client(email="staff-d1-needs@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    with pytest.raises(ValidationError):
        variant_config.save_config(
            actor=actor,
            variant_public_id=variant.public_id,
            payload=VariantConfigPayload(
                mode=IdsVariantConfig.Mode.POD,
                blank_variant_public_id=str(blank_variant.public_id),
                slots=(
                    VariantSlotPayload(
                        placement=BlankPlacementCapability.Placement.FRONT,
                        technique_public_id=str(dtf.public_id),
                        print_reference="",
                    ),
                ),
            ),
            source="test",
        )


def test_on_stock_mode_requires_finished_sku():
    actor, _client = staff_client(email="staff-d1-stock@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    config = variant_config.save_config(
        actor=actor,
        variant_public_id=variant.public_id,
        payload=VariantConfigPayload(mode="on_stock", finished_sku="FINI-TEE-M"),
        source="test",
    )
    assert variant_config.configuration_status(config) == "on_stock"


def test_client_cannot_open_variant_drawer():
    user = get_user_model().objects.create_user(email="client-d1@example.com", password="pass")
    customer = Customer.objects.create(name="Client")
    CustomerMembership.objects.create(customer=customer, user=user)
    actor, _ = staff_client(email="staff-seed@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    client = Client()
    assert client.login(email=user.email, password="pass")
    response = client.get(
        reverse(
            "portal:staff-pod-variant-config",
            kwargs={"variant_public_id": variant.public_id},
        )
    )
    assert response.status_code == 403


def test_apply_template_configures_variant():
    actor, client = staff_client(email="staff-d1-template@example.com", permissions=MANAGE)
    dtf, blank, blank_variant, variant = pod_fixture(actor=actor)
    template = PodRecipeTemplate.objects.create(name="Tee standard", blank=blank)
    PodRecipeTemplateSlot.objects.create(
        template=template,
        placement=BlankPlacementCapability.Placement.FRONT,
        technique=dtf,
        print_reference="template_front.png",
    )
    drawer_url = reverse(
        "portal:staff-pod-variant-config",
        kwargs={"variant_public_id": variant.public_id},
    )
    response = client.post(
        drawer_url,
        {"intent": "apply_template", "template_public_id": str(template.public_id)},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    config = variant.ids_config
    assert config.mode == IdsVariantConfig.Mode.POD
    assert config.blank_variant_id == blank_variant.id
    assert variant_config.configuration_status(config) == CONFIG_STATUS_POD


def test_merchant_can_save_unlocked_config():
    actor, _client = staff_client(email="staff-lock@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    payload = VariantConfigPayload(
        mode=IdsVariantConfig.Mode.ON_STOCK,
        finished_sku="TEE-FIN-1",
    )
    variant_config.save_config(
        actor=None,
        variant_public_id=variant.public_id,
        payload=payload,
        source="merchant_app",
        merchant_actor=True,
    )
    assert variant.ids_config.mode == IdsVariantConfig.Mode.ON_STOCK
    variant_config.save_config(
        actor=actor,
        variant_public_id=variant.public_id,
        payload=VariantConfigPayload(
            mode=IdsVariantConfig.Mode.ON_STOCK,
            finished_sku="TEE-FIN-1",
            staff_locked=True,
        ),
        source="test",
    )
    with pytest.raises(ValidationError, match="verrouillée"):
        variant_config.save_config(
            actor=None,
            variant_public_id=variant.public_id,
            payload=payload,
            source="merchant_app",
            merchant_actor=True,
        )
