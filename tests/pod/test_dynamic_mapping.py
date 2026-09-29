import pytest
from apps.pod.models import IdsVariantConfig, PodRecipe, PrintTechnique
from django.urls import reverse

from tests.pod.test_variant_config import MANAGE, VIEW, catalog, pod_fixture, staff_client

pytestmark = pytest.mark.django_db


def drawer_url(variant):
    return reverse(
        "portal:staff-pod-variant-config", kwargs={"variant_public_id": variant.public_id}
    )


def test_preview_is_read_only_and_keeps_draft_fields():
    actor, client = staff_client(email="dynamic-preview@example.com", permissions=MANAGE)
    _technique, _blank, blank_variant, variant = pod_fixture(actor=actor)
    counts = (IdsVariantConfig.objects.count(), PodRecipe.objects.count())
    response = client.post(
        drawer_url(variant),
        {
            "intent": "preview",
            "mode": "pod",
            "blank_variant_public_id": str(blank_variant.public_id),
            "finished_sku": "DRAFT-SKU",
            "staff_locked": "on",
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert response.context["config"].staff_locked
    assert response.context["config"].finished_sku == "DRAFT-SKU"
    assert len(response.context["slot_rows"]) == 2
    assert "HX-Trigger" not in response
    assert counts == (IdsVariantConfig.objects.count(), PodRecipe.objects.count())
    switched = client.post(
        drawer_url(variant),
        {
            "intent": "preview",
            "mode": "on_stock",
            "blank_variant_public_id": str(blank_variant.public_id),
            "finished_sku": "DRAFT-SKU",
            "staff_locked": "on",
        },
        HTTP_HX_REQUEST="true",
    )
    assert switched.context["config"].blank_variant_id == blank_variant.pk
    assert switched.context["config"].finished_sku == "DRAFT-SKU"
    assert not switched.context["slot_rows"]


def test_save_success_event_and_preview_mode_switch():
    actor, client = staff_client(email="dynamic-save@example.com", permissions=MANAGE)
    _technique, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    url = drawer_url(variant)
    response = client.post(url, {"intent": "save", "mode": "virtual"}, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response["HX-Trigger"] == "pod-config-saved"
    response = client.post(
        url,
        {"intent": "preview", "mode": "on_stock", "finished_sku": "KEEP-ME"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"KEEP-ME" in response.content
    assert not response.context["slot_rows"]
    assert IdsVariantConfig.objects.get(variant=variant).mode == "virtual"


def test_failed_save_keeps_draft_and_never_emits_success_event():
    actor, client = staff_client(email="dynamic-failure@example.com", permissions=MANAGE)
    _technique, _blank, blank_variant, variant = pod_fixture(actor=actor)
    response = client.post(
        drawer_url(variant),
        {
            "intent": "save",
            "mode": "pod",
            "blank_variant_public_id": str(blank_variant.public_id),
            "staff_locked": "on",
            "finished_sku": "UNSAVED",
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 400
    assert response.context["config"].staff_locked
    assert response.context["config"].finished_sku == "UNSAVED"
    assert "HX-Trigger" not in response
    persisted = IdsVariantConfig.objects.get(variant=variant)
    assert persisted.mode == "unmanaged"
    assert not persisted.staff_locked
    assert persisted.finished_sku == ""


def test_preview_invalid_mode_returns_inline_400_and_operator_cannot_preview():
    actor, manager = staff_client(email="dynamic-invalid@example.com", permissions=MANAGE)
    _technique, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    response = manager.post(
        drawer_url(variant), {"intent": "preview", "mode": "unknown"}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 400
    assert "HX-Trigger" not in response
    _operator, client = staff_client(email="dynamic-operator@example.com", permissions=VIEW)
    assert (
        client.post(
            drawer_url(variant), {"intent": "preview", "mode": "virtual"}, HTTP_HX_REQUEST="true"
        ).status_code
        == 403
    )


def test_add_remove_mapping_are_drafts_inherited_from_parent():
    actor, client = staff_client(email="marks-draft@example.com", permissions=MANAGE)
    technique, blank, blank_variant, variant = pod_fixture(actor=actor)
    sibling = catalog.create_variant(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={"sku": "TEE-POD-L", "size_label": "L", "color_name": "Blanc"},
    )
    counts = (IdsVariantConfig.objects.count(), PodRecipe.objects.count())
    data = {
        "intent": "preview",
        "mode": "pod",
        "blank_variant_public_id": str(sibling.public_id),
        "slot_placement": ["front"],
        "slot_technique_public_id": [str(technique.public_id)],
        "slot_enabled": [f"front:{technique.public_id}"],
        "slot_print_reference": [""],
        "slot_source_asset_version_public_id": [""],
        "mapping_placement": "left_chest",
        "mapping_technique": str(technique.public_id),
    }
    response = client.post(drawer_url(variant), data, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert response.context["config"].blank_variant.pk == sibling.pk
    assert len(response.context["mapping_rows"]) == 1
    assert response.context["mapping_zones"][0][0] == "left_chest"
    assert response.context["mapping_techniques"] == [technique]
    assert b"mapping-placement" in response.content
    data["intent"] = "add_slot"
    response = client.post(drawer_url(variant), data, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert len(response.context["mapping_rows"]) == 2
    assert not response.context["mapping_zones"]
    assert "HX-Trigger" not in response
    for name in (
        "slot_placement",
        "slot_technique_public_id",
        "slot_enabled",
        "slot_print_reference",
        "slot_source_asset_version_public_id",
    ):
        data[name].append(
            {
                "slot_placement": "left_chest",
                "slot_technique_public_id": str(technique.public_id),
                "slot_enabled": f"left_chest:{technique.public_id}",
            }.get(name, "")
        )
    data.update(intent="remove_slot", slot_key=f"left_chest:{technique.public_id}")
    response = client.post(drawer_url(variant), data, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert len(response.context["mapping_rows"]) == 1
    assert response.context["mapping_zones"][0][0] == "left_chest"
    assert counts == (IdsVariantConfig.objects.count(), PodRecipe.objects.count())
    assert IdsVariantConfig.objects.get(variant=variant).mode == "unmanaged"


@pytest.mark.parametrize("intent,placement", [("add_slot", "back"), ("remove_slot", "front")])
def test_mapping_rejects_unauthorized_or_required_mark_changes(intent, placement):
    actor, client = staff_client(email=f"marks-{intent}@example.com", permissions=MANAGE)
    technique, _blank, blank_variant, variant = pod_fixture(actor=actor)
    response = client.post(
        drawer_url(variant),
        {
            "intent": intent,
            "mode": "pod",
            "blank_variant_public_id": str(blank_variant.public_id),
            "mapping_placement": placement,
            "mapping_technique": str(technique.public_id),
            "slot_key": f"{placement}:{technique.public_id}",
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 400
    assert response.context["form_error"]
    assert "HX-Trigger" not in response
    assert not PodRecipe.objects.filter(variant_config__variant=variant).exists()


def test_operator_cannot_add_mapping_mark():
    actor, _manager = staff_client(email="marks-owner@example.com", permissions=MANAGE)
    technique, _blank, blank_variant, variant = pod_fixture(actor=actor)
    _operator, client = staff_client(email="marks-operator@example.com", permissions=VIEW)
    response = client.post(
        drawer_url(variant),
        {
            "intent": "add_slot",
            "mode": "pod",
            "blank_variant_public_id": str(blank_variant.public_id),
            "mapping_placement": "left_chest",
            "mapping_technique": str(technique.public_id),
        },
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 403


def test_mapping_offers_multiple_techniques_only_in_their_allowed_zone():
    actor, client = staff_client(email="marks-techniques@example.com", permissions=MANAGE)
    dtf, blank, blank_variant, variant = pod_fixture(actor=actor)
    embroidery = PrintTechnique.objects.create(
        code="test-embroidery", name="Broderie test", export_extension=".dst"
    )
    catalog.add_capability(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={"placement": "left_chest", "technique_public_id": str(embroidery.public_id)},
    )
    data = {
        "intent": "preview",
        "mode": "pod",
        "blank_variant_public_id": str(blank_variant.public_id),
        "mapping_placement": "left_chest",
        "mapping_technique": str(embroidery.public_id),
    }
    response = client.post(drawer_url(variant), data, HTTP_HX_REQUEST="true")
    assert set(response.context["mapping_techniques"]) == {dtf, embroidery}
    assert response.context["mapping_technique"] == str(embroidery.public_id)
    data["intent"] = "add_slot"
    response = client.post(drawer_url(variant), data, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert {(row["placement"], row["technique"]) for row in response.context["mapping_rows"]} == {
        ("front", dtf),
        ("left_chest", embroidery),
    }
    assert response.context["mapping_techniques"] == [dtf]
    data["mapping_placement"] = "front"
    assert client.post(drawer_url(variant), data, HTTP_HX_REQUEST="true").status_code == 400
