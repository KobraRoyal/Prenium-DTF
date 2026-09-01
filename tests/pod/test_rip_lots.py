from __future__ import annotations

from pathlib import Path

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.pod.models import (
    BlankPlacementCapability,
    IdsVariantConfig,
    PodRipWorkItem,
    PrintTechnique,
)
from apps.pod.services import PodRipLotService, VariantConfigService
from apps.pod.services.rip_naming import rip_filename
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from tests.pod.test_variant_config import MANAGE, VIEW, catalog, pod_fixture, staff_client

pytestmark = pytest.mark.django_db

rip = PodRipLotService()
variant_config = VariantConfigService()


def configure_pod(actor, dtf, blank_variant, variant, extra_slots=()):
    slots = [
        VariantSlotPayload(
            placement=BlankPlacementCapability.Placement.FRONT,
            technique_public_id=str(dtf.public_id),
            print_reference="front_hd.png",
        ),
        *extra_slots,
    ]
    return variant_config.save_config(
        actor=actor,
        variant_public_id=variant.public_id,
        payload=VariantConfigPayload(
            mode=IdsVariantConfig.Mode.POD,
            blank_variant_public_id=str(blank_variant.public_id),
            slots=tuple(slots),
        ),
        source="test",
    )


def test_ascii_rip_filename_is_flat_and_unique_pattern():
    name = rip_filename(
        shop_slug="Boutique Acmé!",
        order_number="SO-1042",
        placement="left_chest",
        sku="TEE-BLK-M",
        extension=".png",
    )
    assert name == "boutique-acme_so-1042_left-chest_tee-blk-m.png"
    assert "/" not in name


def test_prepare_lot_writes_flat_rip_and_manifest(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(email="staff-rip@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    client.post(
        reverse("portal:staff-pod-rip-lots"),
        {
            "intent": "enqueue",
            "variant_public_id": str(variant.public_id),
            "shopify_order_number": "SO-1042",
            "quantity": "1",
        },
    )
    response = client.post(reverse("portal:staff-pod-rip-lots"), {"intent": "prepare"})
    assert response.status_code == 302
    lot = rip.list_lots(actor=actor).get()
    rip_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "02_rip"
    files = sorted(p.name for p in rip_dir.iterdir() if p.is_file())
    assert files
    assert all("/" not in name for name in files)
    assert not any(p.is_dir() for p in rip_dir.iterdir())
    manifest = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "00_manifest" / "manifest.json"
    assert manifest.is_file()
    assert "02_rip" in manifest.read_text()
    assert AuditLogEntry.objects.filter(action="pod.rip.lot_prepared").exists()
    of_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "03_of"
    label_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "04_labels"
    assert list(of_dir.glob("*.pdf"))
    assert list(label_dir.glob("*.pdf"))
    unit = lot.units.get()
    pdf = client.get(
        reverse(
            "portal:staff-pod-unit-document",
            kwargs={"unit_public_id": unit.public_id, "document_kind": "of"},
        )
    )
    assert pdf.status_code == 200
    assert pdf["Content-Type"].startswith("application/pdf") or pdf.content[:4] == b"%PDF"


def test_collision_same_shop_so_placement_sku_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="staff-rip-col@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-1042",
    )
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-1042",
    )
    with pytest.raises(ValidationError, match="Collision"):
        rip.prepare_dtf_lot(actor=actor, source="test")


def test_unready_variant_is_skipped(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="staff-rip-skip@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-1",
    )
    with pytest.raises(ValidationError, match="Aucun fichier DTF"):
        rip.prepare_dtf_lot(actor=actor, source="test")
    assert PodRipWorkItem.objects.filter(status=PodRipWorkItem.Status.SKIPPED).exists()


def test_client_cannot_open_rip_lots():
    from apps.customers.models import Customer, CustomerMembership
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(email="client-rip@example.com", password="pass")
    CustomerMembership.objects.create(customer=Customer.objects.create(name="C"), user=user)
    client = Client()
    assert client.login(email=user.email, password="pass")
    assert client.get(reverse("portal:staff-pod-rip-lots")).status_code == 403


def test_view_only_staff_cannot_prepare():
    actor, client = staff_client(email="staff-rip-ro@example.com", permissions=VIEW)
    response = client.post(reverse("portal:staff-pod-rip-lots"), {"intent": "prepare"})
    assert response.status_code == 403


def test_embroidery_lot_writes_flat_technique_directory(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="staff-rip-emb@example.com", permissions=MANAGE)
    dtf, blank, blank_variant, variant = pod_fixture(actor=actor)
    embroidery = PrintTechnique.objects.get(code="embroidery")
    catalog.add_capability(
        actor=actor,
        source="test",
        blank_public_id=blank.public_id,
        data={
            "placement": BlankPlacementCapability.Placement.FRONT,
            "technique_public_id": str(embroidery.public_id),
            "is_required": False,
        },
    )
    configure_pod(
        actor,
        dtf,
        blank_variant,
        variant,
        extra_slots=(
            VariantSlotPayload(
                placement=BlankPlacementCapability.Placement.FRONT,
                technique_public_id=str(embroidery.public_id),
                print_reference="chest.dst",
            ),
        ),
    )
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-EMB",
    )
    lot = rip.prepare_lot(actor=actor, source="test", technique_code="embroidery")
    rip_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "02_embroidery"
    assert rip_dir.is_dir()
    assert not any(p.is_dir() for p in rip_dir.iterdir())
    assert list(rip_dir.glob("*.png"))
