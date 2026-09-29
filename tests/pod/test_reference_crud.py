from __future__ import annotations

from uuid import uuid4

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.inventory.admin import StorageLocationAdmin
from apps.inventory.models import (
    ProductLocationRule,
    SkuKind,
    StockBalance,
    StockOwnerKind,
    StorageLocation,
    Warehouse,
    WarehouseZone,
)
from apps.inventory.services import StockOpsService, WarehouseLayoutService
from apps.pod.admin import (
    BlankAdmin,
    BlankPlacementInline,
    BlankVariantInline,
    PrintTechniqueAdmin,
    ShopifyStoreAdmin,
)
from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    IdsVariantConfig,
    PodRecipe,
    PodRecipeSlot,
    PodRipWorkItem,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services import (
    BlankCatalogService,
    PrintTechniqueService,
    VariantConfigService,
)
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory
from django.urls import reverse

pytestmark = pytest.mark.django_db

techniques = PrintTechniqueService()
catalog = BlankCatalogService()
warehouse = WarehouseLayoutService()
stock = StockOpsService()
variant_configs = VariantConfigService()


def _grant(user, *codenames):
    user.user_permissions.add(
        *(Permission.objects.get(codename=codename) for codename in codenames)
    )


def _staff(*, email: str, manage: bool = True, customer_access: bool = False):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    permissions = ["access_staff_portal", "access_pod_atelier"]
    if manage:
        permissions.extend(("manage_pod_catalog", "manage_warehouse"))
    if customer_access:
        permissions.append("view_customer")
    _grant(user, *permissions)
    return user


def _client_for(user):
    client = Client()
    assert client.login(email=user.email, password="pass")
    return client


def _references(actor, *, suffix: str = "A"):
    technique = techniques.create_technique(
        actor=actor,
        source="test",
        data={
            "code": f"dtf-{suffix.lower()}",
            "name": f"DTF {suffix}",
            "rip_directory": f"02_dtf_{suffix.lower()}",
        },
    )
    blank = catalog.create_blank(
        actor=actor,
        source="test",
        data={"sku": f"BLANK-{suffix}", "name": f"Blank {suffix}", "brand": "IDS"},
    )
    variant = catalog.create_variant(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={
            "sku": f"BLANK-{suffix}-M",
            "size_label": "M",
            "color_name": "Noir",
            "color_hex": "#000000",
        },
    )
    capability = catalog.add_capability(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={
            "placement": BlankPlacementCapability.Placement.FRONT,
            "technique_public_id": technique.public_id,
            "is_required": True,
        },
    )
    warehouse_row = Warehouse.objects.create(
        code=f"wh-{suffix.lower()}",
        name=f"Warehouse {suffix}",
    )
    zone = WarehouseZone.objects.create(
        warehouse=warehouse_row,
        code=f"zone-{suffix.lower()}",
        name=f"Zone {suffix}",
        kind=WarehouseZone.Kind.BLANKS,
    )
    location = StorageLocation.objects.create(
        zone=zone,
        code=f"{suffix}-01-01-A",
        label=f"Bin {suffix}",
    )
    return technique, blank, variant, capability, location


def _queued_item(*, blank_variant, technique):
    store = ShopifyStore.objects.create(
        slug=f"queued-{uuid4().hex[:8]}",
        name="Boutique queued",
        shop_domain=f"queued-{uuid4().hex[:8]}.myshopify.com",
    )
    product = ShopifyProduct.objects.create(
        store=store,
        external_id=uuid4().hex,
        title="Produit queued",
    )
    variant = ShopifyVariant.objects.create(
        product=product,
        external_id=uuid4().hex,
        title="Variante queued",
        sku=f"SHOP-{uuid4().hex[:8]}",
    )
    config = IdsVariantConfig.objects.create(
        variant=variant,
        mode=IdsVariantConfig.Mode.POD,
        blank_variant=blank_variant,
    )
    recipe = PodRecipe.objects.create(variant_config=config)
    PodRecipeSlot.objects.create(
        recipe=recipe,
        placement=BlankPlacementCapability.Placement.FRONT,
        technique=technique,
        is_enabled=True,
        print_reference="front.png",
    )
    return PodRipWorkItem.objects.create(
        store=store,
        variant=variant,
        shopify_order_number=f"SO-{uuid4().hex[:8]}",
        status=PodRipWorkItem.Status.QUEUED,
    )


def test_technique_update_soft_deactivate_and_reactivate_preserve_identity():
    actor = _staff(email="crud-technique@example.com")
    technique, *_rest = _references(actor)
    identity = (technique.code, technique.rip_directory, technique.export_extension)

    for name, active in (("DTF premium", False), ("DTF premium active", True)):
        technique = techniques.update_technique(
            actor=actor,
            source="test",
            technique_public_id=technique.public_id,
            data={"name": name, "is_active": active, "code": "ignored"},
        )
        assert technique.name == name
        assert technique.is_active is active
        assert (technique.code, technique.rip_directory, technique.export_extension) == identity

    assert PrintTechnique.objects.filter(pk=technique.pk).exists()
    assert AuditLogEntry.objects.filter(action="pod.technique.updated").count() == 2


def test_blank_update_soft_deactivate_and_reactivate_preserve_children_and_sku():
    actor = _staff(email="crud-blank@example.com")
    _technique, blank, variant, capability, _location = _references(actor)

    for name, brand, active in (
        ("Blank renommé", "Premium", False),
        ("Blank réactivé", "Premium", True),
    ):
        blank = catalog.update_blank(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            data={"name": name, "brand": brand, "is_active": active, "sku": "IGNORED"},
        )
        assert (blank.name, blank.brand, blank.is_active) == (name, brand, active)

    assert blank.sku == "BLANK-A"
    assert blank.variants.filter(pk=variant.pk).exists()
    assert blank.placement_capabilities.filter(pk=capability.pk).exists()


def test_variant_update_soft_deactivate_and_reactivate_is_scoped_to_parent():
    actor = _staff(email="crud-variant@example.com")
    _technique, blank, variant, _capability, _location = _references(actor)

    for size, color, active in (("L", "Marine", False), ("XL", "Bleu", True)):
        variant = catalog.update_variant(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            variant_public_id=variant.public_id,
            data={
                "size_label": size,
                "color_name": color,
                "color_hex": "#112233",
                "is_active": active,
                "sku": "IGNORED",
            },
        )
        assert (variant.size_label, variant.color_name, variant.is_active) == (
            size,
            color,
            active,
        )

    assert variant.sku == "BLANK-A-M"
    assert variant.blank_id == blank.pk


def test_capability_update_soft_deactivate_and_reactivate_preserve_path():
    actor = _staff(email="crud-capability@example.com")
    technique, blank, _variant, capability, _location = _references(actor)
    identity = (capability.blank_id, capability.placement, capability.technique_id)

    for required, active in ((False, False), (True, True)):
        capability = catalog.update_capability(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            capability_public_id=capability.public_id,
            data={"is_required": required, "is_active": active},
        )
        assert (capability.is_required, capability.is_active) == (required, active)

    assert (capability.blank_id, capability.placement, capability.technique_id) == identity
    assert capability.technique_id == technique.pk


def test_location_update_soft_deactivate_and_reactivate_preserve_code_and_zone():
    actor = _staff(email="crud-location@example.com")
    *_catalog_rows, location = _references(actor)
    identity = (location.code, location.zone_id)

    for label, active in (("Archive", False), ("Actif", True)):
        location = warehouse.update_location(
            actor=actor,
            source="test",
            location_public_id=location.public_id,
            data={"label": label, "is_active": active, "code": "IGNORED"},
        )
        assert (location.label, location.is_active) == (label, active)

    assert (location.code, location.zone_id) == identity


def test_queued_work_blocks_reference_changes_without_deleting_history():
    actor = _staff(email="crud-queued@example.com")
    technique, blank, variant, capability, _location = _references(actor)
    queued = _queued_item(blank_variant=variant, technique=technique)

    attempts = (
        lambda: techniques.update_technique(
            actor=actor,
            source="test",
            technique_public_id=technique.public_id,
            data={"name": "Bloqué", "is_active": True},
        ),
        lambda: catalog.update_blank(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            data={"name": "Bloqué", "brand": blank.brand, "is_active": True},
        ),
        lambda: catalog.update_variant(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            variant_public_id=variant.public_id,
            data={
                "size_label": "XXL",
                "color_name": variant.color_name,
                "color_hex": variant.color_hex,
                "is_active": True,
            },
        ),
        lambda: catalog.update_capability(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            capability_public_id=capability.public_id,
            data={"is_required": False, "is_active": True},
        ),
    )
    for attempt in attempts:
        with pytest.raises(ValidationError, match=r"commande\(s\) POD"):
            attempt()

    assert PodRipWorkItem.objects.filter(pk=queued.pk, status="queued").exists()
    assert Blank.objects.filter(pk=blank.pk).exists()
    assert PrintTechnique.objects.filter(pk=technique.pk).exists()
    assert AuditLogEntry.objects.filter(status=AuditLogEntry.Status.FAILURE).count() >= 4


def test_reserved_stock_and_location_rules_block_deactivation_and_preserve_rows():
    actor = _staff(email="crud-reserved@example.com")
    _technique, blank, variant, _capability, location = _references(actor)
    balance = StockBalance.objects.create(
        sku_kind=SkuKind.BLANK,
        blank_variant=variant,
        location=location,
        owner_kind=StockOwnerKind.ATELIER,
        qty_on_hand=2,
        qty_reserved=1,
    )
    rule = ProductLocationRule.objects.create(
        sku_kind=SkuKind.BLANK,
        blank_variant=variant,
        location=location,
        owner_kind=StockOwnerKind.ATELIER,
    )

    with pytest.raises(ValidationError, match="réservée"):
        catalog.update_blank(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            data={"name": blank.name, "brand": blank.brand, "is_active": False},
        )
    with pytest.raises(ValidationError, match="réservée"):
        catalog.update_variant(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            variant_public_id=variant.public_id,
            data={
                "size_label": variant.size_label,
                "color_name": variant.color_name,
                "color_hex": variant.color_hex,
                "is_active": False,
            },
        )
    with pytest.raises(ValidationError, match="Désactivation impossible"):
        warehouse.update_location(
            actor=actor,
            source="test",
            location_public_id=location.public_id,
            data={"label": location.label, "is_active": False},
        )

    assert StockBalance.objects.filter(pk=balance.pk, qty_reserved=1).exists()
    assert ProductLocationRule.objects.filter(pk=rule.pk).exists()
    assert StorageLocation.objects.filter(pk=location.pk, is_active=True).exists()


def test_reactivation_requires_active_parent_chain():
    actor = _staff(email="crud-parent-active@example.com")
    technique, blank, variant, capability, location = _references(actor)
    variant.is_active = False
    variant.save(update_fields=["is_active", "updated_at"])
    blank.is_active = False
    blank.save(update_fields=["is_active", "updated_at"])
    capability.is_active = False
    capability.save(update_fields=["is_active", "updated_at"])
    location.is_active = False
    location.save(update_fields=["is_active", "updated_at"])
    location.zone.is_active = False
    location.zone.save(update_fields=["is_active", "updated_at"])

    with pytest.raises(ValidationError, match="support vierge est inactif"):
        catalog.update_variant(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            variant_public_id=variant.public_id,
            data={
                "size_label": variant.size_label,
                "color_name": variant.color_name,
                "color_hex": variant.color_hex,
                "is_active": True,
            },
        )
    with pytest.raises(ValidationError, match="support ou la technique"):
        catalog.update_capability(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            capability_public_id=capability.public_id,
            data={"is_required": capability.is_required, "is_active": True},
        )
    with pytest.raises(ValidationError, match="zone ou l’entrepôt"):
        warehouse.update_location(
            actor=actor,
            source="test",
            location_public_id=location.public_id,
            data={"label": location.label, "is_active": True},
        )
    assert technique.is_active is True


def test_uuid_parent_scoping_and_permissions_reject_foreign_or_unauthorized_updates():
    manager = _staff(email="crud-scope-manager@example.com")
    viewer = _staff(email="crud-scope-viewer@example.com", manage=False)
    technique, blank, variant, capability, location = _references(manager, suffix="A")
    _other_technique, other_blank, other_variant, _other_capability, _other_location = (
        _references(manager, suffix="B")
    )

    with pytest.raises(ValidationError, match="Variante support introuvable"):
        catalog.update_variant(
            actor=manager,
            source="test",
            blank_public_id=other_blank.public_id,
            variant_public_id=variant.public_id,
            data={"size_label": "L", "color_name": "Noir", "is_active": True},
        )
    with pytest.raises(ValidationError, match="Pose autorisée introuvable"):
        catalog.update_capability(
            actor=manager,
            source="test",
            blank_public_id=other_blank.public_id,
            capability_public_id=capability.public_id,
            data={"is_required": True, "is_active": True},
        )
    with pytest.raises(ValidationError, match="pour ce support"):
        warehouse.set_blank_default_location(
            actor=manager,
            source="test",
            blank_public_id=blank.public_id,
            variant_public_id=other_variant.public_id,
            location_public_id=location.public_id,
        )
    with pytest.raises(ValidationError, match="Technique introuvable"):
        techniques.update_technique(
            actor=manager,
            source="test",
            technique_public_id=uuid4(),
            data={"name": "Missing", "is_active": True},
        )
    with pytest.raises(PermissionDenied):
        techniques.update_technique(
            actor=viewer,
            source="test",
            technique_public_id=technique.public_id,
            data={"name": "Denied", "is_active": True},
        )
    with pytest.raises(PermissionDenied):
        warehouse.update_location(
            actor=viewer,
            source="test",
            location_public_id=location.public_id,
            data={"label": "Denied", "is_active": True},
        )


def test_invalid_update_rolls_back_and_records_rejection():
    actor = _staff(email="crud-rollback@example.com")
    technique, *_rest = _references(actor)
    original_name = technique.name

    with pytest.raises(ValidationError):
        techniques.update_technique(
            actor=actor,
            source="test",
            technique_public_id=technique.public_id,
            data={"name": "", "is_active": False},
        )

    technique.refresh_from_db()
    assert technique.name == original_name
    assert technique.is_active is True
    assert AuditLogEntry.objects.filter(
        action="pod.technique.update_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_form_error_preserves_safe_fields_and_intent_but_filters_secret_keys():
    actor = _staff(email="crud-form-error@example.com")
    _technique, blank, _variant, _capability, _location = _references(actor)
    client = _client_for(actor)

    response = client.post(
        reverse(
            "portal:staff-pod-blank-detail",
            kwargs={"blank_public_id": blank.public_id},
        ),
        {
            "intent": "update_blank",
            "name": "",
            "brand": "Marque conservée",
            "is_active": "on",
            "api_token": "must-not-be-preserved",
        },
    )

    assert response.status_code == 400
    assert response.context["submitted_intent"] == "update_blank"
    assert response.context["form_data"]["brand"] == "Marque conservée"
    assert "api_token" not in response.context["form_data"]
    blank.refresh_from_db()
    assert blank.name == "Blank A"


def test_unknown_technique_intent_is_rejected_without_writes():
    actor = _staff(email="crud-unknown-intent@example.com")
    client = _client_for(actor)

    response = client.post(
        reverse("portal:staff-pod-techniques"),
        {"intent": "destroy", "name": "Ignored", "credential_hint": "hidden"},
    )

    assert response.status_code == 400
    assert response.context["submitted_intent"] == "destroy"
    assert "credential_hint" not in response.context["form_data"]
    assert PrintTechnique.objects.count() == 0


def test_unknown_blank_and_warehouse_intents_do_not_create_rows():
    actor = _staff(email="crud-unknown-create-intents@example.com")
    client = _client_for(actor)
    default_warehouse = Warehouse.objects.create(code="atl-01", name="Atelier")
    zone = WarehouseZone.objects.create(
        warehouse=default_warehouse,
        code="blanks",
        name="Blanks",
        kind=WarehouseZone.Kind.BLANKS,
    )

    blank_response = client.post(
        reverse("portal:staff-pod-blanks"),
        {
            "intent": "destroy",
            "sku": "MUST-NOT-EXIST",
            "name": "Must not exist",
        },
    )
    location_response = client.post(
        reverse("portal:staff-pod-warehouse"),
        {
            "intent": "destroy",
            "zone_public_id": str(zone.public_id),
            "code": "Z-99-99-Z",
            "label": "Must not exist",
        },
    )

    assert blank_response.status_code == 400
    assert location_response.status_code == 400
    assert not Blank.objects.filter(sku="MUST-NOT-EXIST").exists()
    assert not StorageLocation.objects.filter(code="Z-99-99-Z").exists()


def test_client_role_cannot_access_reference_crud():
    user = get_user_model().objects.create_user(
        email="crud-client-role@example.com",
        password="pass",
    )
    customer = Customer.objects.create(name="Client CRUD")
    CustomerMembership.objects.create(customer=customer, user=user)
    client = _client_for(user)

    assert client.get(reverse("portal:staff-pod-techniques")).status_code == 403
    response = client.post(
        reverse("portal:staff-pod-techniques"),
        {"intent": "create"},
    )
    assert response.status_code == 403


def test_stock_balance_listing_is_permission_gated_searchable_and_eager_loaded(
    django_assert_num_queries,
):
    actor = _staff(email="crud-stock-list@example.com")
    viewer = _staff(email="crud-stock-list-viewer@example.com", manage=False)
    _technique, _blank, variant, _capability, location = _references(actor)
    customer = Customer.objects.create(name="Propriétaire Alpha")
    atelier = StockBalance.objects.create(
        sku_kind=SkuKind.BLANK,
        blank_variant=variant,
        location=location,
        owner_kind=StockOwnerKind.ATELIER,
        qty_on_hand=3,
    )
    customer_balance = StockBalance.objects.create(
        sku_kind=SkuKind.FINISHED,
        finished_sku="FIN-ALPHA",
        location=location,
        owner_kind=StockOwnerKind.CUSTOMER,
        customer=customer,
        qty_on_hand=2,
    )

    with pytest.raises(PermissionDenied):
        stock.list_balances(actor=viewer)
    with django_assert_num_queries(1):
        rows = list(stock.list_balances(actor=actor, query="Alpha"))
        assert [(row.pk, row.customer.name) for row in rows] == [
            (customer_balance.pk, "Propriétaire Alpha")
        ]
    assert list(stock.list_balances(actor=actor, query=location.code)) == [
        atelier,
        customer_balance,
    ]


def test_customer_owned_stock_audit_uses_customer_public_id_not_integer_id():
    actor = _staff(email="crud-stock-audit@example.com", customer_access=True)
    _technique, _blank, variant, _capability, _location = _references(actor)
    default_warehouse = Warehouse.objects.create(code="atl-01", name="Atelier")
    client_zone = WarehouseZone.objects.create(
        warehouse=default_warehouse,
        code="client",
        name="Client",
        kind=WarehouseZone.Kind.CLIENT,
    )
    location = StorageLocation.objects.create(
        zone=client_zone,
        code="C-01-01-A",
        label="Client",
    )
    customer = Customer.objects.create(name="Client audit")

    stock.receive_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=variant.public_id,
        location_public_id=location.public_id,
        quantity=1,
        owner_kind=StockOwnerKind.CUSTOMER,
        customer_public_id=customer.public_id,
    )

    event = AuditLogEntry.objects.get(action="inventory.stock.received")
    assert event.metadata["customer_public_id"] == str(customer.public_id)
    assert str(customer.pk) not in event.metadata.values()


def test_customer_owned_stock_mutation_requires_customer_permission():
    actor = _staff(email="crud-stock-customer-denied@example.com")
    _technique, _blank, variant, _capability, _location = _references(actor)
    default_warehouse = Warehouse.objects.create(code="atl-01", name="Atelier")
    client_zone = WarehouseZone.objects.create(
        warehouse=default_warehouse,
        code="client",
        name="Client",
        kind=WarehouseZone.Kind.CLIENT,
    )
    location = StorageLocation.objects.create(
        zone=client_zone,
        code="C-02-01-A",
        label="Client",
    )
    customer = Customer.objects.create(name="Client non autorisé")

    with pytest.raises(PermissionDenied):
        stock.receive_blank(
            actor=actor,
            source="test",
            blank_variant_public_id=variant.public_id,
            location_public_id=location.public_id,
            quantity=1,
            owner_kind=StockOwnerKind.CUSTOMER,
            customer_public_id=customer.public_id,
        )

    assert not StockBalance.objects.filter(customer=customer).exists()
    assert AuditLogEntry.objects.filter(
        action="inventory.stock.customer_permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_sensitive_reference_admins_cannot_bypass_audited_services():
    user = get_user_model().objects.create_superuser(
        email="crud-admin-hardening@example.com",
        password="pass",
    )
    request = RequestFactory().get("/admin/")
    request.user = user

    technique_admin = PrintTechniqueAdmin(PrintTechnique, admin.site)
    blank_admin = BlankAdmin(Blank, admin.site)
    variant_inline = BlankVariantInline(Blank, admin.site)
    capability_inline = BlankPlacementInline(Blank, admin.site)
    location_admin = StorageLocationAdmin(StorageLocation, admin.site)
    store_admin = ShopifyStoreAdmin(ShopifyStore, admin.site)

    for model_admin in (technique_admin, blank_admin, location_admin):
        assert model_admin.has_add_permission(request) is False
        assert model_admin.has_delete_permission(request) is False
        assert "is_active" in model_admin.readonly_fields
    assert {"photo", "photo_thumb"}.issubset(blank_admin.readonly_fields)
    assert variant_inline.has_add_permission(request) is False
    assert variant_inline.can_delete is False
    assert {"is_active", "photo", "photo_thumb"}.issubset(
        variant_inline.readonly_fields
    )
    assert capability_inline.has_add_permission(request) is False
    assert capability_inline.can_delete is False
    assert {"is_required", "is_active"}.issubset(capability_inline.readonly_fields)

    store_form = store_admin.get_form(request)
    assert "is_active" in store_admin.readonly_fields
    assert "webhook_secret" not in store_form.base_fields
    assert "access_token_encrypted" not in store_form.base_fields


def test_pod_readiness_and_selectors_require_the_full_active_reference_chain():
    from tests.pod.test_variant_config import ready_png

    actor = _staff(email="crud-readiness@example.com")
    technique, blank, blank_variant, capability, _location = _references(actor)
    customer = Customer.objects.create(name="Client readiness")
    store = ShopifyStore.objects.create(
        customer=customer,
        slug="readiness-store",
        name="Readiness store",
        shop_domain="readiness-store.myshopify.com",
    )
    product = ShopifyProduct.objects.create(
        store=store,
        external_id="readiness-product",
        title="Produit readiness",
    )
    variant = ShopifyVariant.objects.create(
        product=product,
        external_id="readiness-variant",
        title="Variante readiness",
        sku="READY-M",
    )
    config = IdsVariantConfig.objects.create(
        variant=variant,
        mode=IdsVariantConfig.Mode.POD,
        blank_variant=blank_variant,
    )
    recipe = PodRecipe.objects.create(variant_config=config)
    version = ready_png(actor=actor, customer=customer, name="readiness.png")
    PodRecipeSlot.objects.create(
        recipe=recipe,
        placement=capability.placement,
        technique=technique,
        is_enabled=True,
        source_asset_version=version,
        print_reference=version.original_filename,
    )

    def status():
        current = IdsVariantConfig.objects.select_related(
            "variant__product__store",
            "blank_variant__blank",
            "recipe",
        ).get(pk=config.pk)
        return variant_configs.configuration_status(current)

    assert status() == "pod"
    for row in (blank_variant, blank, technique, capability):
        row.is_active = False
        row.save(update_fields=["is_active", "updated_at"])
        assert status() == "needs_config"
        row.is_active = True
        row.save(update_fields=["is_active", "updated_at"])
        assert status() == "pod"

    technique.is_active = False
    technique.save(update_fields=["is_active", "updated_at"])
    context = variant_configs.drawer_context(actor=actor, variant=variant)
    assert context["slot_rows"] == []

    blank.is_active = False
    blank.save(update_fields=["is_active", "updated_at"])
    context = variant_configs.drawer_context(actor=actor, variant=variant)
    assert blank_variant not in list(context["blank_variants"])
