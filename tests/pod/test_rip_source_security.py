from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest
from apps.customers.models import Customer
from apps.pod.models import (
    PodDriveHdSource,
    PodRipLot,
    PodRipWorkItem,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.rip_source import RipSourceService
from apps.uploads.models import Asset, AssetVersion
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.db.models.deletion import ProtectedError
from PIL import Image

from tests.pod.test_rip_lots import (
    MANAGE,
    PNG_BYTES,
    attach_ready_source,
    configure_pod,
    confirm_session,
    open_pick_session_for_items,
    pick_sessions,
    pod_fixture,
    rip,
    staff_client,
)

pytestmark = pytest.mark.django_db


def _approve_internal_drive_source(*, actor, slot, version, content):
    source = PodDriveHdSource.objects.create(
        customer=version.customer,
        selected_by=actor,
        drive_file_id=f"internal-hd-{version.public_id}",
        drive_version="1",
        canonical_url=f"https://drive.google.com/file/d/internal-hd-{version.public_id}/view",
        original_filename=version.original_filename,
        mime_type=version.mime_type,
        size_bytes=len(content),
        md5_checksum=hashlib.md5(content, usedforsecurity=False).hexdigest(),
        status=PodDriveHdSource.Status.READY,
        asset_version=version,
    )
    slot.source_drive_hd = source
    slot.save(update_fields=["source_drive_hd", "updated_at"])
    return source


def _dtf_source_bytes(extension: str) -> bytes:
    if extension in {".pdf", ".ai"}:
        document = pymupdf.open()
        page = document.new_page(width=72, height=72)
        page.draw_rect(pymupdf.Rect(8, 8, 64, 64), color=(0, 0, 0), fill=(0, 0, 0))
        content = document.tobytes()
        document.close()
        return content
    if extension == ".eps":
        return (
            b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 72 72\n%%Pages: 1\n"
            b"newpath 8 8 moveto 64 8 lineto 64 64 lineto closepath fill\nshowpage\n%%EOF\n"
        )
    if extension in {".tif", ".tiff"}:
        output = BytesIO()
        Image.new("RGBA", (12, 12), (0, 0, 0, 0)).save(output, format="TIFF")
        return output.getvalue()
    raise AssertionError(extension)


@pytest.mark.parametrize(
    ("extension", "mime_type"),
    [
        (".pdf", "application/pdf"),
        (".ai", "application/pdf"),
        (".eps", "application/postscript"),
        (".tif", "image/tiff"),
        (".tiff", "image/tiff"),
    ],
)
def test_dtf_rip_passes_original_file_through_unchanged(tmp_path, settings, extension, mime_type):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email=f"rip-{extension[1:]}@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    content = _dtf_source_bytes(extension)
    version = attach_ready_source(
        actor=actor,
        slot=slot,
        customer=variant.product.store.customer,
        content=content,
    )
    version.original_filename = f"artwork{extension}"
    version.mime_type = mime_type
    version.save(update_fields=["original_filename", "mime_type", "updated_at"])
    drive_source = (
        _approve_internal_drive_source(actor=actor, slot=slot, version=version, content=content)
        if extension in {".pdf", ".ai", ".eps"}
        else None
    )
    destination = tmp_path / f"shop_so-123_front_tee{extension}"

    with transaction.atomic():
        staged = RipSourceService().stage(
            version=version,
            store=variant.product.store,
            technique=dtf,
            destination=destination,
            drive_source=drive_source,
        )
        RipSourceService.publish(staged=staged, destination=destination)

    assert destination.read_bytes() == content
    assert staged.checksum_sha256 == hashlib.sha256(content).hexdigest()


def test_dtf_lot_uses_source_extension_and_records_format_without_drive_id(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="rip-pdf-lot@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    content = _dtf_source_bytes(".pdf")
    version = attach_ready_source(
        actor=actor,
        slot=slot,
        customer=variant.product.store.customer,
        content=content,
    )
    version.original_filename = "original.pdf"
    version.mime_type = "application/pdf"
    version.save(update_fields=["original_filename", "mime_type", "updated_at"])
    _approve_internal_drive_source(actor=actor, slot=slot, version=version, content=content)
    item = _queued_item(actor=actor, variant=variant, number="SO-PDF-LOT")
    session, location = open_pick_session_for_items(
        actor=actor, blank_variant=blank_variant, items=[item]
    )
    confirm_session(actor=actor, session=session, location=location)

    lot = rip.prepare_dtf_lot(
        actor=actor,
        source="test.security",
        work_item_public_ids=[str(item.public_id)],
    )

    rip_dir = Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "02_rip"
    output_files = [entry for entry in rip_dir.iterdir() if entry.is_file()]
    assert len(output_files) == 1
    assert output_files[0].suffix == ".pdf"
    assert output_files[0].read_bytes() == content
    assert lot.nas_relative_path == session.code
    rip_file = lot.files.get()
    assert rip_file.source_print_reference.endswith(".pdf")
    assert rip_file.checksum_sha256
    assert not (Path(tmp_path) / "pod_rip" / lot.nas_relative_path / "00_manifest").exists()


def test_client_uploaded_vector_cannot_be_mapped_or_exported_without_internal_drive_provenance(
    tmp_path, settings
):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-untrusted-vector@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    content = _dtf_source_bytes(".pdf")
    version = attach_ready_source(
        actor=actor,
        slot=slot,
        customer=variant.product.store.customer,
        content=content,
    )
    version.original_filename = "client-vector.pdf"
    version.mime_type = "application/pdf"
    version.save(update_fields=["original_filename", "mime_type", "updated_at"])

    with pytest.raises(ValidationError, match="bibliothèque Drive HD"):
        RipSourceService().resolve(slot=slot, store=variant.product.store, technique=dtf)
    with transaction.atomic(), pytest.raises(ValidationError, match="bibliothèque Drive HD"):
        RipSourceService().stage(
            version=version,
            store=variant.product.store,
            technique=dtf,
            destination=tmp_path / "rejected.pdf",
        )
    assert not list(tmp_path.glob("*.part"))


def test_dtf_warning_analysis_remains_blocked(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-warning@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    version = config.recipe.slots.get().source_asset_version
    version.analysis_status = AssetVersion.AnalysisStatus.WARNING
    version.save(update_fields=["analysis_status", "updated_at"])

    with pytest.raises(ValidationError, match="READY"):
        RipSourceService().resolve(
            slot=config.recipe.slots.get(),
            store=variant.product.store,
            technique=dtf,
        )


def test_dtf_pdf_multipage_cannot_be_staged(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-multipage@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    document = pymupdf.open()
    document.new_page()
    document.new_page()
    content = document.tobytes()
    document.close()
    version = attach_ready_source(
        actor=actor,
        slot=slot,
        customer=variant.product.store.customer,
        content=content,
    )
    version.original_filename = "multipage.pdf"
    version.mime_type = "application/pdf"
    version.save(update_fields=["original_filename", "mime_type", "updated_at"])
    drive_source = _approve_internal_drive_source(
        actor=actor, slot=slot, version=version, content=content
    )

    with transaction.atomic(), pytest.raises(ValidationError, match="exactement une page"):
        RipSourceService().stage(
            version=version,
            store=variant.product.store,
            technique=dtf,
            destination=tmp_path / "multipage.pdf",
            drive_source=drive_source,
        )
    assert not list(tmp_path.glob("*.part"))


def _queued_item(*, actor, variant, number):
    return rip.enqueue(
        actor=actor,
        source="test.security",
        variant_public_id=variant.public_id,
        shopify_order_number=number,
    )


def test_legacy_text_reference_without_asset_is_not_printable(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-legacy@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    assert slot.print_reference
    slot.source_asset_version = None
    slot.save(update_fields=["source_asset_version", "updated_at"])
    item = _queued_item(actor=actor, variant=variant, number="SO-LEGACY")

    with pytest.raises(ValidationError, match="ancienne référence texte"):
        RipSourceService().resolve(slot=slot, store=variant.product.store, technique=dtf)
    with pytest.raises(ValidationError, match="NEEDS_CONFIG"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test.security",
            work_item_public_ids=[str(item.public_id)],
        )

    item.refresh_from_db()
    assert item.status == PodRipWorkItem.Status.SKIPPED
    assert not PodRipLot.objects.exists()


def test_cross_customer_asset_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-tenant@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    other_customer = Customer.objects.create(name="Autre client")
    foreign_version = attach_ready_source(
        actor=actor,
        slot=slot,
        customer=other_customer,
    )
    assert foreign_version.customer != variant.product.store.customer
    item = _queued_item(actor=actor, variant=variant, number="SO-TENANT")

    with pytest.raises(ValidationError, match="n'appartient pas au client"):
        RipSourceService().resolve(slot=slot, store=variant.product.store, technique=dtf)
    with pytest.raises(ValidationError, match="NEEDS_CONFIG"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test.security",
            work_item_public_ids=[str(item.public_id)],
        )

    assert not PodRipLot.objects.exists()


def test_missing_source_file_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="rip-missing@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    version = config.recipe.slots.get().source_asset_version
    item = _queued_item(actor=actor, variant=variant, number="SO-MISSING")
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)
    version.file.storage.delete(version.file.name)

    with pytest.raises(ValidationError, match="introuvable dans le stockage"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test.security",
            work_item_public_ids=[str(item.public_id)],
        )

    assert not PodRipLot.objects.exists()


def test_corrupted_source_hash_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="rip-corrupt@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    version = config.recipe.slots.get().source_asset_version
    item = _queued_item(actor=actor, variant=variant, number="SO-CORRUPT")
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)
    with version.file.storage.open(version.file.name, "wb") as output:
        output.write(b"X" * len(PNG_BYTES))

    with pytest.raises(ValidationError, match="SHA-256 incohérent"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test.security",
            work_item_public_ids=[str(item.public_id)],
        )

    assert not PodRipLot.objects.exists()


def test_source_archived_after_planning_is_rechecked_before_staging(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-race@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    source = RipSourceService().resolve(slot=slot, store=variant.product.store, technique=dtf)
    source.asset.is_archived = True
    source.asset.save(update_fields=["is_archived", "updated_at"])
    with transaction.atomic(), pytest.raises(ValidationError, match="archivé"):
        RipSourceService().stage(
            version=source,
            store=variant.product.store,
            technique=dtf,
            destination=tmp_path / "output.png",
        )
    assert not (tmp_path / "output.png").exists()


def test_unsupported_pdf_rip_format_is_refused(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-pdf-block@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    dtf.export_extension = ".pdf"
    dtf.save(update_fields=["export_extension", "updated_at"])
    with pytest.raises(ValidationError, match="Seul le PNG"):
        RipSourceService().resolve(
            slot=config.recipe.slots.get(),
            store=variant.product.store,
            technique=dtf,
        )


def test_png_with_valid_signature_but_bad_crc_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(email="rip-bad-crc@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    damaged = bytearray(PNG_BYTES)
    damaged[-16] ^= 1
    version = attach_ready_source(
        actor=actor,
        slot=slot,
        customer=variant.product.store.customer,
        content=bytes(damaged),
    )
    with transaction.atomic(), pytest.raises(ValidationError, match="PNG.*invalide"):
        RipSourceService().stage(
            version=version,
            store=variant.product.store,
            technique=dtf,
            destination=tmp_path / "damaged.png",
        )
    assert not list(tmp_path.glob("*.part"))


def test_rip_file_protects_exact_source_version(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="rip-provenance@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    version = slot.source_asset_version
    item = _queued_item(actor=actor, variant=variant, number="SO-PROVENANCE")
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)

    lot = rip.prepare_dtf_lot(
        actor=actor,
        source="test.security",
        work_item_public_ids=[str(item.public_id)],
    )
    rip_file = lot.files.get()
    assert rip_file.source_asset_version == version
    assert rip_file.checksum_sha256 == hashlib.sha256(PNG_BYTES).hexdigest()
    slot.source_asset_version = None
    slot.save(update_fields=["source_asset_version", "updated_at"])

    with pytest.raises(ProtectedError):
        version.delete()


def test_pick_session_rejects_mixed_stores(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="pick-store-scope@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    second_customer = Customer.objects.create(name="Client deux")
    second_store = ShopifyStore.objects.create(
        customer=second_customer,
        slug="pick-second",
        name="Pick second",
        shop_domain="pick-second.myshopify.com",
    )
    second_product = ShopifyProduct.objects.create(
        store=second_store,
        external_id="pick-product-2",
        title="Pick product 2",
    )
    second_variant = ShopifyVariant.objects.create(
        product=second_product,
        external_id="pick-variant-2",
        title="Pick variant 2",
        sku="PICK-2",
    )
    configure_pod(actor, dtf, blank_variant, second_variant)
    first = _queued_item(actor=actor, variant=variant, number="SO-PICK-1")
    second = _queued_item(actor=actor, variant=second_variant, number="SO-PICK-2")

    with pytest.raises(ValidationError, match="une seule boutique"):
        pick_sessions.open_session(
            actor=actor,
            source="test.security",
            work_item_public_ids=[str(first.public_id), str(second.public_id)],
        )


def test_declared_png_with_non_png_signature_is_rejected(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="rip-signature@example.com",
        permissions=MANAGE + ("manage_warehouse",),
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    config = configure_pod(actor, dtf, blank_variant, variant)
    slot = config.recipe.slots.get()
    customer = variant.product.store.customer
    content = b"not-a-real-png"
    asset = Asset.objects.create(customer=customer, created_by=actor, name="fake.png")
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=actor,
        version_number=1,
        file=SimpleUploadedFile("fake.png", content, content_type="image/png"),
        original_filename="fake.png",
        mime_type="image/png",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    slot.source_asset_version = version
    slot.save(update_fields=["source_asset_version", "updated_at"])
    item = _queued_item(actor=actor, variant=variant, number="SO-SIGNATURE")
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    confirm_session(actor=actor, session=session, location=location)

    with pytest.raises(ValidationError, match="signature"):
        rip.prepare_dtf_lot(
            actor=actor,
            source="test.security",
            work_item_public_ids=[str(item.public_id)],
        )
