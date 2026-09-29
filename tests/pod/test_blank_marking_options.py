from __future__ import annotations

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.pod.models import (
    Blank,
    BlankPlacementCapability,
    BlankVariant,
    IdsVariantConfig,
    MarkingZone,
    PodRecipe,
    PodRecipeSlot,
    PodRipWorkItem,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.blank_marking_options import (
    BlankMarkingOptionsService,
    capabilities_for_blank,
)
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError

pytestmark = pytest.mark.django_db

service = BlankMarkingOptionsService()


def test_backfill_splits_only_active_capabilities_and_preserves_legacy_rows():
    from importlib import import_module

    from django.apps import apps

    blank = _blank()
    empty_blank = _blank("BLANK-EMPTY")
    inactive_technique = _technique("legacy-inactive", is_active=False)
    dtf = _technique()
    active = BlankPlacementCapability.objects.create(
        blank=blank,
        technique=inactive_technique,
        placement="front",
        is_required=True,
    )
    inactive = BlankPlacementCapability.objects.create(
        blank=blank,
        technique=dtf,
        placement="back",
        is_active=False,
    )
    import_module(
        "apps.pod.migrations.0018_blank_marking_options"
    ).seed_and_backfill_marking_options(apps, None)
    blank.refresh_from_db()
    empty_blank.refresh_from_db()
    assert blank.marking_options_configured
    assert empty_blank.marking_options_configured
    assert set(blank.allowed_zones.values_list("code", flat=True)) == {"front"}
    assert list(blank.allowed_techniques.all()) == [inactive_technique]
    assert not empty_blank.allowed_zones.exists()
    assert BlankPlacementCapability.objects.filter(
        public_id=active.public_id, is_required=True
    ).exists()
    assert BlankPlacementCapability.objects.filter(
        public_id=inactive.public_id, is_active=False
    ).exists()


def _actor(django_user_model, *, manage=True):
    actor = django_user_model.objects.create_user(
        email=f"marking-{django_user_model.objects.count()}@example.com",
        password="pass",
        is_staff=True,
    )
    permissions = [Permission.objects.get(codename="access_staff_portal")]
    if manage:
        permissions.append(Permission.objects.get(codename="manage_pod_catalog"))
    actor.user_permissions.add(*permissions)
    return actor


def _zone(code="front", name="Devant", display_order=0, is_active=True):
    return MarkingZone.objects.update_or_create(
        code=code,
        defaults={
            "name": name,
            "display_order": display_order,
            "is_active": is_active,
        },
    )[0]


def _technique(code="dtf", name="DTF", display_order=0, is_active=True):
    return PrintTechnique.objects.create(
        code=code,
        name=name,
        display_order=display_order,
        is_active=is_active,
    )


def _blank(sku="BLANK-1"):
    return Blank.objects.create(sku=sku, name=sku)


def test_configured_options_produce_cartesian_capabilities_without_legacy_couples():
    blank = _blank()
    front = _zone()
    back = _zone("back", "Dos", 1)
    dtf = _technique()
    embroidery = _technique("embroidery", "Broderie", 1)
    blank.allowed_zones.set([front, back])
    blank.allowed_techniques.set([dtf, embroidery])
    blank.marking_options_configured = True
    blank.save(update_fields=["marking_options_configured", "updated_at"])

    capabilities = capabilities_for_blank(blank)

    assert BlankPlacementCapability.objects.count() == 0
    assert {
        (capability.placement, capability.technique.code, capability.is_required)
        for capability in capabilities
    } == {
        ("front", "dtf", False),
        ("front", "embroidery", False),
        ("back", "dtf", False),
        ("back", "embroidery", False),
    }
    assert capabilities[0].get_placement_display() == "Devant"


def test_unconfigured_blank_falls_back_to_active_legacy_capabilities():
    blank = _blank()
    dtf = _technique()
    inactive_technique = _technique("inactive", "Inactive", is_active=False)
    BlankPlacementCapability.objects.create(
        blank=blank,
        technique=dtf,
        placement=BlankPlacementCapability.Placement.FRONT,
        is_required=True,
    )
    BlankPlacementCapability.objects.create(
        blank=blank,
        technique=inactive_technique,
        placement=BlankPlacementCapability.Placement.BACK,
    )

    capabilities = capabilities_for_blank(blank)

    assert len(capabilities) == 1
    assert capabilities[0].placement == "front"
    assert capabilities[0].technique == dtf
    assert capabilities[0].is_required is True


def test_save_requires_staff_catalog_permission_and_audits_rejection(django_user_model):
    actor = _actor(django_user_model, manage=False)
    blank = _blank()

    with pytest.raises(PermissionDenied):
        service.save(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            zone_public_ids=[],
            technique_public_ids=[],
        )

    assert AuditLogEntry.objects.filter(
        action="pod.blank_marking_options.permission_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_save_rejects_noncanonical_uuid_and_audits(django_user_model):
    actor = _actor(django_user_model)
    blank = _blank()
    zone = _zone()

    with pytest.raises(ValidationError, match="Zone de marquage invalide"):
        service.save(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            zone_public_ids=[zone.public_id.hex],
            technique_public_ids=[],
        )

    assert AuditLogEntry.objects.filter(
        action="pod.blank_marking_options.save_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_save_normalizes_duplicates_and_accepts_an_explicit_empty_selection(
    django_user_model,
):
    actor = _actor(django_user_model)
    blank = _blank()
    zone = _zone()
    technique = _technique()

    service.save(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        zone_public_ids=[str(zone.public_id), str(zone.public_id)],
        technique_public_ids=[str(technique.public_id), str(technique.public_id)],
    )
    saved = service.save(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        zone_public_ids=[],
        technique_public_ids=[],
    )

    assert saved.marking_options_configured is True
    assert saved.allowed_zones.count() == 0
    assert saved.allowed_techniques.count() == 0
    audit = AuditLogEntry.objects.filter(action="pod.blank_marking_options.saved").latest(
        "created_at"
    )
    assert audit.metadata["previous"]["zones"] == [str(zone.public_id)]
    assert audit.metadata["changes"]["zones"] == []


def test_selection_context_derives_legacy_union_without_writing():
    blank = _blank()
    front = _zone()
    dtf = _technique()
    BlankPlacementCapability.objects.create(
        blank=blank,
        technique=dtf,
        placement=BlankPlacementCapability.Placement.FRONT,
    )

    context = service.selection_context(blank)

    blank.refresh_from_db()
    assert blank.marking_options_configured is False
    assert context["selected_marking_zones"] == [str(front.public_id)]
    assert context["selected_marking_techniques"] == [str(dtf.public_id)]


def test_save_rejects_inactive_selections(django_user_model):
    actor = _actor(django_user_model)
    blank = _blank()
    inactive_zone = _zone(is_active=False)

    with pytest.raises(ValidationError, match="inactive ou introuvable"):
        service.save(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            zone_public_ids=[str(inactive_zone.public_id)],
            technique_public_ids=[],
        )


def test_save_refuses_removal_used_by_enabled_recipe_and_reports_queued_work(
    django_user_model,
):
    actor = _actor(django_user_model)
    blank = _blank()
    zone = _zone()
    technique = _technique()
    blank.allowed_zones.set([zone])
    blank.allowed_techniques.set([technique])
    blank.marking_options_configured = True
    blank.save(update_fields=["marking_options_configured", "updated_at"])
    blank_variant = BlankVariant.objects.create(
        blank=blank,
        sku="BLANK-1-M",
        size_label="M",
        color_name="Noir",
    )
    store = ShopifyStore.objects.create(
        slug="marking-store",
        name="Marking store",
        shop_domain="marking-store.myshopify.com",
    )
    product = ShopifyProduct.objects.create(
        store=store,
        external_id="product-1",
        title="Produit",
    )
    variant = ShopifyVariant.objects.create(
        product=product,
        external_id="variant-1",
        title="Variante",
    )
    config = IdsVariantConfig.objects.create(
        variant=variant,
        mode=IdsVariantConfig.Mode.POD,
        blank_variant=blank_variant,
    )
    recipe = PodRecipe.objects.create(variant_config=config)
    PodRecipeSlot.objects.create(
        recipe=recipe,
        placement=zone.code,
        technique=technique,
        is_enabled=True,
    )
    PodRipWorkItem.objects.create(
        store=store,
        variant=variant,
        shopify_order_number="1001",
    )

    with pytest.raises(ValidationError, match="file de production"):
        service.save(
            actor=actor,
            source="test",
            blank_public_id=blank.public_id,
            zone_public_ids=[],
            technique_public_ids=[str(technique.public_id)],
        )

    blank.refresh_from_db()
    assert list(blank.allowed_zones.all()) == [zone]
    assert AuditLogEntry.objects.filter(
        action="pod.blank_marking_options.save_rejected",
        target_public_id=blank.public_id,
    ).exists()
