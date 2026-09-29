from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.inventory.models import StorageLocation, WarehouseZone
from apps.inventory.services import StockOpsService, WarehouseLayoutService
from apps.pod.models import (
    BlankPlacementCapability,
    IdsVariantConfig,
    PodPickSessionLine,
    PodRipLot,
    PodRipWorkItem,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services import PodRipLotService, VariantConfigService
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.rip_naming import rip_filename
from apps.pod.services.variant_config_contract import VariantConfigPayload, VariantSlotPayload
from apps.uploads.models import Asset, AssetVersion
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from tests.pod.test_variant_config import MANAGE, VIEW, catalog, pod_fixture, staff_client

pytestmark = pytest.mark.django_db

rip = PodRipLotService()
variant_config = VariantConfigService()
pick_sessions = PodPickSessionService()
stock = StockOpsService()
warehouse = WarehouseLayoutService()

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


def ensure_store_customer(variant, *, name="Client POD"):
    store = variant.product.store
    if store.customer_id is None:
        store.customer = Customer.objects.create(name=name)
        store.save(update_fields=["customer", "updated_at"])
    return store.customer


def attach_ready_source(*, actor, slot, customer, content=PNG_BYTES):
    extension = slot.technique.export_extension.lower()
    filename = f"{slot.placement}{extension}"
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
        ".dst": "application/x-dst",
    }
    asset = Asset.objects.create(
        customer=customer,
        created_by=actor,
        name=filename,
    )
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=actor,
        version_number=1,
        file=SimpleUploadedFile(
            filename,
            content,
            content_type=mime_types.get(extension, "application/octet-stream"),
        ),
        original_filename=filename,
        mime_type=mime_types.get(extension, "application/octet-stream"),
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    slot.source_asset_version = version
    slot.save(update_fields=["source_asset_version", "updated_at"])
    return version


def configure_pod(actor, dtf, blank_variant, variant, extra_slots=()):
    slots = [
        VariantSlotPayload(
            placement=BlankPlacementCapability.Placement.FRONT,
            technique_public_id=str(dtf.public_id),
            print_reference="front_hd.png",
        ),
        *extra_slots,
    ]
    config = variant_config.save_config(
        actor=actor,
        variant_public_id=variant.public_id,
        payload=VariantConfigPayload(
            mode=IdsVariantConfig.Mode.POD,
            blank_variant_public_id=str(blank_variant.public_id),
            slots=tuple(slots),
        ),
        source="test",
    )
    customer = ensure_store_customer(variant)
    for slot in config.recipe.slots.select_related("technique"):
        attach_ready_source(actor=actor, slot=slot, customer=customer)
    return config


def open_pick_session_for_items(*, actor, blank_variant, items, bin_code="A-01-01-A"):
    warehouse.ensure_default_layout(actor=actor)
    zone = WarehouseZone.objects.get(kind=WarehouseZone.Kind.BLANKS, warehouse__code="atl-01")
    location = StorageLocation.objects.filter(code=bin_code).first()
    if location is None:
        location = warehouse.create_location(
            actor=actor,
            source="test",
            data={
                "zone_public_id": str(zone.public_id),
                "code": bin_code,
                "label": bin_code,
            },
        )
    warehouse.set_blank_default_location(
        actor=actor,
        source="test",
        variant_public_id=blank_variant.public_id,
        location_public_id=location.public_id,
    )
    stock.receive_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        location_public_id=location.public_id,
        quantity=sum(int(item.quantity) for item in items),
    )
    session = pick_sessions.open_session(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id) for item in items],
    )
    return session, location


def confirm_session(*, actor, session, location):
    for line in session.lines.order_by("sequence"):
        pick_sessions.confirm_pick(
            actor=actor,
            source="test",
            scan_identifier=line.scan_identifier,
            scanned_bin_code=location.code,
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


def test_prepare_lot_writes_session_rip_visuals_only(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(
        email="staff-rip@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
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
    item = PodRipWorkItem.objects.get(shopify_order_number="SO-1042")
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)
    response = client.post(reverse("portal:staff-pod-rip-lots"), {"intent": "prepare"})
    assert response.status_code == 302
    lot = rip.list_lots(actor=actor).get()
    assert lot.customer == variant.product.store.customer
    assert lot.nas_relative_path == session.code
    rip_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "02_rip"
    rip_paths = sorted(p for p in rip_dir.iterdir() if p.is_file())
    files = [p.name for p in rip_paths]
    assert files
    assert rip_paths[0].read_bytes() == PNG_BYTES
    assert all("/" not in name for name in files)
    assert not any(p.is_dir() for p in rip_dir.iterdir())
    assert not (Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "00_manifest").exists()
    assert not (Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "03_of").exists()
    assert not (Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "04_labels").exists()
    assert lot.files.get().source_asset_version_id is not None
    assert lot.files.get().checksum_sha256 == hashlib.sha256(PNG_BYTES).hexdigest()
    assert AuditLogEntry.objects.filter(action="pod.rip.lot_prepared").exists()
    unit = lot.units.get()
    assert unit.scan_identifier == session.lines.get().scan_identifier
    assert unit.of_relative_path == ""
    assert unit.label_relative_path == ""
    pdf = client.get(
        reverse(
            "portal:staff-pod-unit-document",
            kwargs={"unit_public_id": unit.public_id, "document_kind": "of"},
        )
    )
    assert pdf.status_code == 404


def test_lot_files_are_removed_when_document_creation_rolls_back(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-rollback@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-ROLLBACK",
    )
    session, location = open_pick_session_for_items(
        actor=actor, blank_variant=blank_variant, items=[item]
    )
    confirm_session(actor=actor, session=session, location=location)

    def fail_after_export(self, *, lot, planned):
        raise RuntimeError("document failure")

    monkeypatch.setattr(
        "apps.pod.services.rip_lots.PodUnitDocumentService.create_units_for_lot",
        fail_after_export,
    )
    with pytest.raises(RuntimeError, match="document failure"):
        rip.prepare_dtf_lot(actor=actor, source="test")
    assert not PodRipLot.objects.exists()
    assert not list((tmp_path / "pod_rip").rglob("*.png"))
    assert not list((tmp_path / "pod_rip").rglob("*.pdf"))


def test_collision_same_shop_so_placement_sku_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-col@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    first = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-1042",
    )
    second = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-1042",
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[first, second],
    )
    confirm_session(actor=actor, session=session, location=location)
    with pytest.raises(ValidationError, match="Collision"):
        rip.prepare_dtf_lot(actor=actor, source="test")


def test_unready_variant_is_skipped(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="staff-rip-skip@example.com", permissions=MANAGE)
    _dtf, _blank, _blank_variant, variant = pod_fixture(actor=actor)
    ensure_store_customer(variant)
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


def test_prepare_lot_respects_work_item_selection(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-sel@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    first = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-SEL-1",
    )
    second = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-SEL-2",
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[first],
    )
    confirm_session(actor=actor, session=session, location=location)
    lot = rip.prepare_dtf_lot(
        actor=actor,
        source="test",
        work_item_public_ids=[str(first.public_id)],
    )
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == PodRipWorkItem.Status.INCLUDED
    assert second.status == PodRipWorkItem.Status.QUEUED
    assert lot.units.filter(work_item=first).exists()
    assert not lot.units.filter(work_item=second).exists()


def test_prepare_lot_rejects_empty_selection(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="staff-rip-empty-sel@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-EMPTY",
    )
    with pytest.raises(ValidationError, match="Sélectionnez au moins une commande"):
        rip.prepare_dtf_lot(actor=actor, source="test", work_item_public_ids=[])


def test_embroidery_lot_writes_flat_technique_directory(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-emb@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
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
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-EMB",
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)
    lot = rip.prepare_lot(actor=actor, source="test", technique_code="embroidery")
    rip_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "02_embroidery"
    assert rip_dir.is_dir()
    assert not any(p.is_dir() for p in rip_dir.iterdir())
    assert list(rip_dir.glob("*.png"))


def test_prepare_lot_allowed_before_pick_when_labels_exist(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-pick-gate@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-PICK-GATE",
        quantity=2,
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    lot = rip.prepare_dtf_lot(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    assert lot.units.count() == 2
    for line in session.lines.order_by("sequence"):
        assert line.unit_id is not None
        assert line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED


def test_prepare_lot_requires_pick_labels(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-label-gate@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-LABEL-GATE",
        quantity=1,
    )
    with pytest.raises(ValidationError, match="Étiquettes picking manquantes"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test",
            work_item_public_ids=[str(item.public_id)],
        )


def test_quantity_cannot_drop_below_active_pick_lines(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-quantity-floor@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-QTY-FLOOR",
        quantity=2,
    )
    open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )

    with pytest.raises(ValidationError, match="ne peut pas passer sous 2"):
        rip.set_queued_quantity(
            actor=actor,
            source="test",
            work_item_public_id=item.public_id,
            quantity=1,
        )

    item.refresh_from_db()
    assert item.quantity == 2


def test_prepare_lot_rejects_an_already_prepared_selection(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-repeat@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-ONCE",
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)
    rip.prepare_dtf_lot(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )

    with pytest.raises(ValidationError, match="déjà préparée"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test",
            work_item_public_ids=[str(item.public_id)],
        )


def test_prepare_lot_rejects_mixed_store_selection(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-rip-store-scope@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    other_store = ShopifyStore.objects.create(
        slug="second-store",
        name="Second store",
        shop_domain="second-store.myshopify.com",
    )
    other_product = ShopifyProduct.objects.create(
        store=other_store,
        external_id="product-2",
        title="Second product",
    )
    other_variant = ShopifyVariant.objects.create(
        product=other_product,
        external_id="variant-2",
        title="Second variant",
        sku="SECOND-SKU",
    )
    configure_pod(actor, dtf, blank_variant, other_variant)
    first = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-STORE-1",
    )
    second = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=other_variant.public_id,
        shopify_order_number="SO-STORE-2",
    )

    with pytest.raises(ValidationError, match="une seule boutique"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test",
            work_item_public_ids=[str(first.public_id), str(second.public_id)],
        )


def test_hub_pick_scan_debits_stock_and_displays_piece_status():
    actor, client = staff_client(
        email="staff-hub-pick@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-HUB-PICK",
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    line = session.lines.get()

    response = client.post(
        reverse("portal:staff-pod-hub"),
        {
            "intent": "confirm_pick",
            "scan_identifier": line.scan_identifier.lower(),
            "scanned_bin_code": location.code.lower(),
        },
    )

    assert response.status_code == 302
    line.refresh_from_db()
    assert line.reservation_status == PodPickSessionLine.ReservationStatus.PICKED
    page = client.get(reverse("portal:staff-pod-hub"))
    body = page.content.decode()
    assert line.scan_identifier in body
    assert location.code in body
    assert "Prélevée" in body
    assert f"session={session.public_id}" in response["Location"]
    assert "Sortie de stock" in body
    assert "pod-pick-station" in body


def test_hub_pick_scan_returns_clear_htmx_error_and_keeps_reservation():
    actor, client = staff_client(
        email="staff-hub-pick-error@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-HUB-PICK-ERROR",
    )
    session, _location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    line = session.lines.get()

    response = client.post(
        reverse("portal:staff-pod-hub"),
        {
            "intent": "confirm_pick",
            "scan_identifier": line.scan_identifier,
            "scanned_bin_code": "Z-99-99-Z",
        },
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert "Bin incorrect" in response.content.decode()
    line.refresh_from_db()
    assert line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED


def test_view_only_staff_cannot_confirm_pick_from_hub():
    manager, _manager_client = staff_client(
        email="staff-hub-pick-manager@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=manager)
    configure_pod(manager, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=manager,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-HUB-PICK-DENIED",
    )
    session, location = open_pick_session_for_items(
        actor=manager,
        blank_variant=blank_variant,
        items=[item],
    )
    line = session.lines.get()
    _viewer, client = staff_client(email="staff-hub-pick-viewer@example.com", permissions=VIEW)

    response = client.post(
        reverse("portal:staff-pod-hub"),
        {
            "intent": "confirm_pick",
            "scan_identifier": line.scan_identifier,
            "scanned_bin_code": location.code,
        },
    )

    assert response.status_code == 403
    line.refresh_from_db()
    assert line.reservation_status == PodPickSessionLine.ReservationStatus.RESERVED


def test_rip_ready_work_items_after_full_pick(tmp_path, settings):
    actor, _client = staff_client(
        email="staff-rip-ready@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    settings.MEDIA_ROOT = tmp_path
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-RIP-READY",
        quantity=1,
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    ready = rip.rip_ready_work_items_for_session(session=session)
    assert [entry.public_id for entry in ready] == [item.public_id]
    confirm_session(actor=actor, session=session, location=location)
    assert [entry.public_id for entry in rip.rip_ready_work_items_for_session(session=session)] == [
        item.public_id
    ]
    rip.prepare_dtf_lot(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    assert rip.rip_ready_work_items_for_session(session=session) == []
