import pytest
from apps.customers.models import Customer
from apps.pod.models import BlankPlacementCapability, MarkingZone, PodRecipeSlot, PrintTechnique
from apps.pod.services.blank_marking_options import BlankMarkingOptionsService
from apps.pod.services.variant_config import VariantConfigService
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections
from django.urls import reverse

from tests.pod.test_dynamic_mapping import drawer_url
from tests.pod.test_variant_config import (
    MANAGE,
    VIEW,
    catalog,
    pod_fixture,
    ready_png,
    staff_client,
)

pytestmark = pytest.mark.django_db


def test_independent_lists_allow_new_recipe_pair_and_are_inherited(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(email="independent-mapping@example.com", permissions=MANAGE)
    dtf, blank, blank_variant, variant = pod_fixture(actor=actor)
    store = variant.product.store
    store.customer = Customer.objects.create(name="Client recette indépendante")
    store.save(update_fields=["customer", "updated_at"])
    other_technique = PrintTechnique.objects.create(code="other-png", name="Autre technique PNG")
    zones = list(MarkingZone.objects.filter(code__in=["front", "back"]))
    legacy_count = BlankPlacementCapability.objects.filter(blank=blank).count()
    url = reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank.public_id})
    response = client.post(
        url,
        {
            "intent": "marking_options",
            "zone_public_ids": [str(zone.public_id) for zone in zones],
            "technique_public_ids": [str(dtf.public_id), str(other_technique.public_id)],
        },
    )
    assert response.status_code == 302
    assert BlankPlacementCapability.objects.filter(blank=blank).count() == legacy_count
    child = catalog.create_variant(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={"sku": "TEE-INDEPENDENT-L", "size_label": "L", "color_name": "Rouge"},
    )
    draft = {"intent": "preview", "mode": "pod", "blank_variant_public_id": str(child.public_id)}
    preview = client.post(drawer_url(variant), draft, HTTP_HX_REQUEST="true")
    assert preview.status_code == 200
    assert not preview.context["mapping_rows"]
    assert len(preview.context["slot_rows"]) == 4
    assert not any(row["is_required"] for row in preview.context["slot_rows"])
    draft.update(
        intent="add_slot",
        mapping_placement="back",
        mapping_technique=str(other_technique.public_id),
    )
    added = client.post(drawer_url(variant), draft, HTTP_HX_REQUEST="true")
    assert added.status_code == 200
    assert len(added.context["mapping_rows"]) == 1
    version = ready_png(actor=actor, customer=variant.product.store.customer)
    saved = client.post(
        drawer_url(variant),
        {
            "intent": "save",
            "mode": "pod",
            "blank_variant_public_id": str(child.public_id),
            "slot_placement": ["back"],
            "slot_technique_public_id": [str(other_technique.public_id)],
            "slot_enabled": [f"back:{other_technique.public_id}"],
            "slot_source_asset_version_public_id": [str(version.public_id)],
        },
        HTTP_HX_REQUEST="true",
    )
    assert saved.status_code == 200
    assert saved.context["status"] == "pod"
    slot = PodRecipeSlot.objects.get(recipe__variant_config__variant=variant)
    assert slot.placement == "back"
    assert slot.technique == other_technique
    assert slot.source_asset_version == version
    # The other child inherits exactly the same parent lists, with no copied combinations.
    draft.update(intent="preview", blank_variant_public_id=str(blank_variant.public_id))
    assert len(client.post(drawer_url(variant), draft).context["slot_rows"]) == 4


def test_options_form_preserves_multiple_selections_on_error_and_rejects_legacy_pair_route():
    actor, client = staff_client(email="independent-form@example.com", permissions=MANAGE)
    dtf, blank, _child, _variant = pod_fixture(actor=actor)
    zones = list(MarkingZone.objects.filter(code__in=["front", "back"]))
    url = reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank.public_id})
    response = client.post(
        url,
        {
            "intent": "marking_options",
            "zone_public_ids": [str(zone.public_id) for zone in zones],
            "technique_public_ids": [str(dtf.public_id), "not-a-uuid"],
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 400
    assert response.context["selected_marking_zones"] == [str(zone.public_id) for zone in zones]
    blank.refresh_from_db()
    assert not blank.marking_options_configured
    assert (
        client.post(
            url,
            {
                "intent": "capability",
                "placement": "back",
                "technique_public_id": str(dtf.public_id),
            },
        ).status_code
        == 400
    )


def test_operator_cannot_update_independent_options():
    actor, _manager = staff_client(email="independent-owner@example.com", permissions=MANAGE)
    _dtf, blank, _child, _variant = pod_fixture(actor=actor)
    _operator, client = staff_client(email="independent-reader@example.com", permissions=VIEW)
    url = reverse("portal:staff-pod-blank-detail", kwargs={"blank_public_id": blank.public_id})
    assert client.post(url, {"intent": "marking_options"}).status_code == 403


@pytest.mark.django_db(transaction=True)
def test_options_removal_and_recipe_save_are_serialized_on_postgres(tmp_path, settings):
    if connection.vendor != "postgresql":
        pytest.skip("Requires PostgreSQL row locks")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.contrib.auth import get_user_model

    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="independent-locks@example.com", permissions=MANAGE)
    dtf, blank, child, variant = pod_fixture(actor=actor)
    store = variant.product.store
    store.customer = Customer.objects.create(name="Client verrou partagé")
    store.save(update_fields=["customer", "updated_at"])
    front, _ = MarkingZone.objects.get_or_create(code="front", defaults={"name": "Devant"})
    back, _ = MarkingZone.objects.get_or_create(code="back", defaults={"name": "Dos"})
    service = BlankMarkingOptionsService()
    service.save(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        zone_public_ids=[front.public_id, back.public_id],
        technique_public_ids=[dtf.public_id],
    )
    version = ready_png(actor=actor, customer=store.customer)

    def payload(placement):
        return VariantConfigPayload(
            mode="pod",
            blank_variant_public_id=str(child.public_id),
            slots=(
                VariantSlotPayload(
                    placement=placement,
                    technique_public_id=str(dtf.public_id),
                    source_asset_version_public_id=str(version.public_id),
                ),
            ),
        )

    VariantConfigService().save_config(
        actor=actor, source="test", variant_public_id=variant.public_id, payload=payload("front")
    )
    barrier = Barrier(2)

    def attempt(action):
        close_old_connections()
        try:
            user = get_user_model().objects.get(pk=actor.pk)
            barrier.wait(timeout=10)
            if action == "recipe":
                VariantConfigService().save_config(
                    actor=user,
                    source="test",
                    variant_public_id=variant.public_id,
                    payload=payload("back"),
                )
            else:
                service.save(
                    actor=user,
                    source="test",
                    blank_public_id=blank.public_id,
                    zone_public_ids=[front.public_id],
                    technique_public_ids=[dtf.public_id],
                )
            return "saved"
        except ValidationError:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["recipe", "options"]))
    assert sorted(results) == ["rejected", "saved"]
    slot = PodRecipeSlot.objects.get(recipe__variant_config__variant=variant)
    blank.refresh_from_db()
    assert blank.allowed_zones.filter(code=slot.placement).exists()
