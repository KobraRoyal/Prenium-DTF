from __future__ import annotations

import base64
import hashlib
import html
from types import SimpleNamespace

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.pod.models import (
    BlankPlacementCapability,
    IdsVariantConfig,
    PodDriveHdSource,
    PodRecipe,
    PodRecipeSlot,
    PodRecipeTemplate,
    PodRecipeTemplateSlot,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services import (
    BlankCatalogService,
    PrintTechniqueService,
    ShopifyCatalogService,
    VariantConfigService,
)
from apps.pod.services.variant_config import CONFIG_STATUS_NEEDS_CONFIG, CONFIG_STATUS_POD
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from apps.uploads.models import Asset, AssetVersion
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db

catalog = BlankCatalogService()
techniques = PrintTechniqueService()
shopify = ShopifyCatalogService()
variant_config = VariantConfigService()

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


def ready_png(*, actor, customer, name="front.png"):
    asset = Asset.objects.create(customer=customer, created_by=actor, name=name)
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=actor,
        version_number=1,
        file=SimpleUploadedFile(name, PNG_BYTES, content_type="image/png"),
        original_filename=name,
        mime_type="image/png",
        size_bytes=len(PNG_BYTES),
        sha256=hashlib.sha256(PNG_BYTES).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    return version


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


MANAGE = ("access_pod_atelier", "manage_pod_catalog", "operate_pod_production")
VIEW = ("access_pod_atelier",)


def test_empty_catalogue_get_does_not_create_demo_data():
    _actor, client = staff_client(email="staff-d1-empty@example.com", permissions=MANAGE)

    response = client.get(reverse("portal:staff-pod-catalog"))

    assert response.status_code == 200
    assert ShopifyStore.objects.count() == 0
    assert ShopifyProduct.objects.count() == 0
    assert ShopifyVariant.objects.count() == 0
    assert IdsVariantConfig.objects.count() == 0


def test_demo_catalog_generates_a_fresh_unpredictable_webhook_secret():
    actor, _client = staff_client(email="staff-d1-secret@example.com", permissions=MANAGE)

    first_product = shopify.ensure_demo_catalog(actor=actor)
    first_secret = first_product.store.webhook_secret
    first_product.store.delete()
    second_product = shopify.ensure_demo_catalog(actor=actor)
    second_secret = second_product.store.webhook_secret

    assert len(first_secret) >= 64
    assert len(second_secret) >= 64
    assert first_secret != second_secret
    assert first_secret != "local-pod-webhook-secret"
    assert second_secret != "local-pod-webhook-secret"


def test_catalogue_lists_variants_with_needs_config_badge():
    actor, client = staff_client(email="staff-d1-list@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    response = client.get(reverse("portal:staff-pod-catalog"))
    assert response.status_code == 200
    assert b"needs_config" in response.content or b"unmanaged" in response.content
    assert variant.sku.encode() in response.content


def test_variant_drawer_saves_legacy_references_as_needs_config():
    actor, client = staff_client(email="staff-d1-save@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    drawer_url = reverse(
        "portal:staff-pod-variant-config",
        kwargs={"variant_public_id": variant.public_id},
    )
    get_response = client.get(drawer_url)
    assert get_response.status_code == 200
    assert "Configuration de variante" in get_response.content.decode()
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
    assert variant_config.configuration_status(config) == CONFIG_STATUS_NEEDS_CONFIG
    assert config.recipe.slots.count() == 2
    assert AuditLogEntry.objects.filter(action="pod.variant_config.saved").exists()


def test_pod_without_required_print_reference_stays_needs_config():
    actor, _client = staff_client(email="staff-d1-needs@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = variant_config.save_config(
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
    assert variant_config.configuration_status(config) == CONFIG_STATUS_NEEDS_CONFIG


def test_drawer_selects_exact_customer_asset_version_and_rejects_cross_customer():
    actor, client = staff_client(email="staff-d1-assets@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    customer = Customer.objects.create(name="Client visuels")
    other_customer = Customer.objects.create(name="Autre client visuels")
    store = variant.product.store
    store.customer = customer
    store.save(update_fields=["customer", "updated_at"])
    allowed = ready_png(actor=actor, customer=customer, name="front-client.png")
    foreign = ready_png(actor=actor, customer=other_customer, name="front-foreign.png")
    drawer_url = reverse(
        "portal:staff-pod-variant-config",
        kwargs={"variant_public_id": variant.public_id},
    )
    preview = client.get(
        drawer_url,
        {"blank_variant_public_id": str(blank_variant.public_id)},
    )
    assert preview.status_code == 200
    assert str(allowed.public_id) in preview.content.decode()
    assert str(foreign.public_id) not in preview.content.decode()

    data = {
        "intent": "save",
        "mode": "pod",
        "blank_variant_public_id": str(blank_variant.public_id),
        "slot_placement": [BlankPlacementCapability.Placement.FRONT],
        "slot_technique_public_id": [str(dtf.public_id)],
        "slot_required_0": "1",
        "slot_source_asset_version_public_id": [str(foreign.public_id)],
    }
    rejected = client.post(drawer_url, data, HTTP_HX_REQUEST="true")
    assert rejected.status_code == 400
    assert "n'appartient pas au client" in html.unescape(rejected.content.decode())

    data["slot_source_asset_version_public_id"] = [str(allowed.public_id)]
    accepted = client.post(drawer_url, data, HTTP_HX_REQUEST="true")
    assert accepted.status_code == 200
    config = ShopifyVariant.objects.get(pk=variant.pk).ids_config
    assert config.recipe.slots.get().source_asset_version == allowed
    assert variant_config.configuration_status(config) == CONFIG_STATUS_POD


def test_drawer_masks_foreign_drive_source_even_when_legacy_slot_links_it(monkeypatch):
    actor, client = staff_client(email="staff-drive-mask@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    own_customer = Customer.objects.create(name="Client propriétaire boutique")
    other_customer = Customer.objects.create(name="Client autre")
    variant.product.store.customer = own_customer
    variant.product.store.save(update_fields=["customer", "updated_at"])
    config = variant_config.get_config(variant)
    config.mode = IdsVariantConfig.Mode.POD
    config.blank_variant = blank_variant
    config.save(update_fields=["mode", "blank_variant", "updated_at"])
    recipe = PodRecipe.objects.create(variant_config=config)
    foreign = PodDriveHdSource.objects.create(
        customer=other_customer,
        drive_file_id="foreign-private-drive-id",
        canonical_url="https://drive.google.com/file/d/foreign-private-drive-id/view",
        original_filename="foreign-secret-filename.png",
        mime_type="image/png",
        size_bytes=100,
        md5_checksum="a" * 32,
        drive_version="1",
        status=PodDriveHdSource.Status.FAILED,
        last_error="foreign-secret-error",
    )
    PodRecipeSlot.objects.create(
        recipe=recipe,
        placement=BlankPlacementCapability.Placement.FRONT,
        technique=dtf,
        source_drive_hd=foreign,
    )
    monkeypatch.setattr(
        variant_config.drive_hd_source,
        "list_options",
        lambda **_kwargs: SimpleNamespace(options=(), configured=True, error=""),
    )

    response = client.get(
        reverse(
            "portal:staff-pod-variant-config",
            kwargs={"variant_public_id": variant.public_id},
        )
    )

    assert response.status_code == 200
    rendered = response.content.decode()
    for secret in (
        "foreign-private-drive-id",
        "foreign-secret-filename.png",
        "foreign-secret-error",
    ):
        assert secret not in rendered


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
    assert variant_config.configuration_status(config) == CONFIG_STATUS_NEEDS_CONFIG


def test_store_template_is_hidden_and_rejected_for_other_store():
    actor, client = staff_client(email="staff-template-scope@example.com", permissions=MANAGE)
    _dtf, blank, blank_variant, variant = pod_fixture(actor=actor)
    other_store = ShopifyStore.objects.create(
        slug="other-template-store",
        name="Autre boutique",
        shop_domain="other-template-store.myshopify.com",
    )
    private_template = PodRecipeTemplate.objects.create(
        name="Privé autre boutique", blank=blank, store=other_store
    )
    drawer_url = reverse(
        "portal:staff-pod-variant-config",
        kwargs={"variant_public_id": variant.public_id},
    )
    drawer = client.get(drawer_url, {"blank_variant_public_id": str(blank_variant.public_id)})
    assert drawer.status_code == 200
    assert "Privé autre boutique" not in drawer.content.decode()
    initial_mode = variant.ids_config.mode
    denied = client.post(
        drawer_url,
        {"intent": "apply_template", "template_public_id": str(private_template.public_id)},
        HTTP_HX_REQUEST="true",
    )
    assert denied.status_code == 400
    variant.ids_config.refresh_from_db()
    assert variant.ids_config.mode == initial_mode


def test_merchant_write_is_disabled_until_customer_scope_exists():
    actor, _client = staff_client(email="staff-lock@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    payload = VariantConfigPayload(
        mode=IdsVariantConfig.Mode.ON_STOCK,
        finished_sku="TEE-FIN-1",
    )
    with pytest.raises(ValidationError, match="périmètre Customer"):
        variant_config.save_config(
            actor=None,
            variant_public_id=variant.public_id,
            payload=payload,
            source="merchant_app",
            merchant_actor=True,
        )
    variant.refresh_from_db()
    assert variant.ids_config.mode == IdsVariantConfig.Mode.UNMANAGED
    assert AuditLogEntry.objects.filter(
        action="pod.variant_config.save_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_operator_catalogue_product_and_drawer_gets_are_denied_without_mutation():
    store = ShopifyStore.objects.create(
        name="Boutique lecture seule",
        slug="boutique-lecture-seule",
        shop_domain="lecture-seule.myshopify.com",
    )
    product = ShopifyProduct.objects.create(
        store=store,
        external_id="read-only-product",
        title="Produit lecture seule",
    )
    variant = ShopifyVariant.objects.create(
        product=product,
        external_id="read-only-variant",
        title="Noir / M",
        sku="READ-ONLY-M",
    )
    _actor, client = staff_client(email="staff-read-only@example.com", permissions=VIEW)

    urls = (
        reverse("portal:staff-pod-catalog"),
        reverse(
            "portal:staff-pod-catalog-product",
            kwargs={"product_public_id": product.public_id},
        ),
        reverse(
            "portal:staff-pod-variant-config",
            kwargs={"variant_public_id": variant.public_id},
        ),
    )
    for url in urls:
        response = client.get(url)
        assert response.status_code == 403
        assert IdsVariantConfig.objects.filter(variant=variant).count() == 0
        assert PodRecipe.objects.count() == 0
