import hashlib
from decimal import Decimal
from uuid import uuid4

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import B2BOrderProjectService, ProjectDomainError
from apps.gang_sheets.forms import GangSheetSiteSettingsForm
from apps.gang_sheets.models import (
    GangSheet,
    GangSheetDriveSync,
    GangSheetItem,
    GangSheetSiteSettings,
    GangSheetSourceAsset,
)
from apps.gang_sheets.services import (
    GangSheetDomainError,
    GangSheetGeometryService,
    GangSheetRenderService,
    GangSheetService,
)
from apps.gang_sheets.services.cropping import AutoCropResult, CropBox
from apps.orders.models import Order
from apps.uploads.models import Asset, AssetAnalysis, AssetVersion, OrderUpload
from apps.uploads.services.asset_analysis import AssetAnalysisService
from apps.uploads.services.assets import AssetService
from django.contrib import admin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from .helpers import attach_png_asset, create_customer_scope, mark_gang_sheet_drive_synced

pytestmark = pytest.mark.django_db


def test_standalone_sheet_does_not_require_an_order_project():
    user, customer, _project = create_customer_scope(email="standalone@example.com")

    sheet = GangSheetService().create_sheet(
        customer=customer,
        actor=user,
        name="Planche autonome",
    )

    assert sheet.customer == customer
    assert sheet.project is None
    assert sheet.source_assets.count() == 0


def test_occurrence_uses_the_cropped_physical_dimensions():
    user, customer, project = create_customer_scope(email="cropped-size@example.com")
    asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Dimensions crop")
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
        crop_x="0.10",
        crop_y="0.20",
        crop_width="0.50",
        crop_height="0.40",
    )

    item = service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )

    assert item.width_mm == Decimal("50.00")
    assert item.height_mm == Decimal("20.00")


def test_source_quantity_preserves_existing_positions_and_tracks_actual_occurrences():
    user, customer, project = create_customer_scope(email="quantity-source@example.com")
    asset, _version = attach_png_asset(
        customer=customer, project=project, user=user, width_mm="70.00", height_mm="35.00"
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Quantités")
    entry = sheet.source_assets.get(asset=asset)
    original, count = service.set_source_quantity(
        sheet=sheet,
        source_asset_public_id=entry.public_id,
        quantity="1",
        expected_revision=sheet.revision,
        actor=user,
    )
    assert count == 1
    first = sheet.items.get()
    original_position = (first.x_mm, first.y_mm, first.rotation)
    updated, count = service.set_source_quantity(
        sheet=sheet,
        source_asset_public_id=entry.public_id,
        quantity="3",
        expected_revision=original.revision,
        actor=user,
    )
    first.refresh_from_db()
    assert count == 3
    assert sheet.items.count() == 3
    assert (first.x_mm, first.y_mm, first.rotation) == original_position
    assert not service.geometry.issues(sheet=updated, items=list(sheet.items.all()))
    no_change, count = service.set_source_quantity(
        sheet=sheet,
        source_asset_public_id=entry.public_id,
        quantity="3",
        expected_revision=updated.revision,
        actor=user,
    )
    assert count == 3
    assert no_change.revision == updated.revision
    reduced, count = service.set_source_quantity(
        sheet=sheet,
        source_asset_public_id=entry.public_id,
        quantity="0",
        expected_revision=updated.revision,
        actor=user,
    )
    assert count == 0
    assert sheet.items.count() == 0
    assert reduced.revision == updated.revision + 1
    assert AuditLogEntry.objects.filter(action="gang_sheet.source_quantity_updated").count() == 3


def test_source_quantity_rolls_back_if_new_occurrences_do_not_fit():
    user, customer, project = create_customer_scope(email="quantity-no-space@example.com")
    asset, _version = attach_png_asset(
        customer=customer, project=project, user=user, width_mm="500.00", height_mm="100.00"
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Quantité limitée")
    entry = sheet.source_assets.get(asset=asset)
    sheet.maximum_height_mm = Decimal("100.00")
    sheet.save(update_fields=["maximum_height_mm"])
    revision = sheet.revision
    with pytest.raises(GangSheetDomainError) as error:
        service.set_source_quantity(
            sheet=sheet,
            source_asset_public_id=entry.public_id,
            quantity="2",
            expected_revision=revision,
            actor=user,
        )
    assert error.value.code == "QUANTITY_NO_SPACE"
    sheet.refresh_from_db()
    assert sheet.revision == revision
    assert sheet.items.count() == 0
    assert not AuditLogEntry.objects.filter(action="gang_sheet.source_quantity_updated").exists()


def test_source_quantity_counts_old_asset_versions_and_adds_only_current_version():
    user, customer, project = create_customer_scope(email="quantity-versions@example.com")
    asset, old_version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Versions source")
    entry = sheet.source_assets.get(asset=asset)
    old_item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=old_version.public_id, actor=user
    )
    sheet.refresh_from_db()
    with old_version.file.open("rb") as file:
        content = file.read()
    current = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=user,
        version_number=2,
        file=SimpleUploadedFile("logo-v2.png", content, content_type="image/png"),
        original_filename="logo-v2.png",
        mime_type="image/png",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = current
    asset.save(update_fields=["current_version", "updated_at"])
    updated, count = service.set_source_quantity(
        sheet=sheet,
        source_asset_public_id=entry.public_id,
        quantity="2",
        expected_revision=sheet.revision,
        actor=user,
    )
    assert count == 2
    assert sheet.items.filter(asset_version=old_version, public_id=old_item.public_id).count() == 1
    assert sheet.items.filter(asset_version=current).count() == 1
    serialized = service.serialize_sheet(updated, preview_url_resolver=lambda _version: "")
    assert {item["asset_public_id"] for item in serialized["items"]} == {str(asset.public_id)}


def test_source_quantity_rejects_invalid_stale_foreign_and_grouped_decrease():
    user, customer, project = create_customer_scope(email="quantity-guard@example.com")
    asset, _version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Quantité contrôlée")
    entry = sheet.source_assets.get(asset=asset)
    other_user, other_customer, other_project = create_customer_scope(
        email="quantity-foreign@example.com"
    )
    foreign_asset, _ = attach_png_asset(
        customer=other_customer, project=other_project, user=other_user
    )
    foreign_sheet = service.create_sheet(project=other_project, actor=other_user, name="Autre")
    foreign_entry = foreign_sheet.source_assets.get(asset=foreign_asset)
    for quantity, revision, source_id, expected in (
        ("1.5", sheet.revision, entry.public_id, "INVALID_QUANTITY"),
        ("201", sheet.revision, entry.public_id, "INVALID_QUANTITY"),
        ("1", sheet.revision + 1, entry.public_id, "STALE_REVISION"),
        ("1", sheet.revision, foreign_entry.public_id, "SOURCE_ASSET_NOT_FOUND"),
    ):
        with pytest.raises(GangSheetDomainError) as error:
            service.set_source_quantity(
                sheet=sheet,
                source_asset_public_id=source_id,
                quantity=quantity,
                expected_revision=revision,
                actor=user,
            )
        assert error.value.code == expected
    updated, _ = service.set_source_quantity(
        sheet=sheet,
        source_asset_public_id=entry.public_id,
        quantity="1",
        expected_revision=sheet.revision,
        actor=user,
    )
    first = sheet.items.get()
    first.layout_group_id = uuid4()
    first.save(update_fields=["layout_group_id"])
    with pytest.raises(GangSheetDomainError) as error:
        service.set_source_quantity(
            sheet=sheet,
            source_asset_public_id=entry.public_id,
            quantity="0",
            expected_revision=updated.revision,
            actor=user,
        )
    assert error.value.code == "GROUPED_ITEMS"
    assert sheet.items.count() == 1


def test_existing_source_crop_is_updated_audited_and_versions_the_sheet():
    user, customer, project = create_customer_scope(email="crop-existing@example.com")
    asset, _version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Crop existant")
    source_asset = sheet.source_assets.get(asset=asset)
    initial_revision = sheet.revision

    updated_sheet, updated_source = service.update_source_asset_crop(
        sheet=sheet,
        source_asset_public_id=source_asset.public_id,
        crop=CropBox.from_values(x="0.10", y="0.20", width="0.60", height="0.50"),
        expected_revision=initial_revision,
        actor=user,
        source="test",
    )

    updated_source.refresh_from_db()
    assert updated_source.crop_x == Decimal("0.100000")
    assert updated_source.crop_y == Decimal("0.200000")
    assert updated_source.crop_width == Decimal("0.600000")
    assert updated_source.crop_height == Decimal("0.500000")
    assert updated_source.effective_width_mm == Decimal("60.00")
    assert updated_source.effective_height_mm == Decimal("25.00")
    assert updated_sheet.revision == initial_revision + 1
    event = AuditLogEntry.objects.get(action="gang_sheet.source_crop_updated")
    assert event.target_public_id == sheet.public_id
    assert event.metadata["source_asset_public_id"] == str(source_asset.public_id)
    assert event.metadata["previous_crop"] == {
        "x": "0.000000",
        "y": "0.000000",
        "width": "1.000000",
        "height": "1.000000",
    }
    assert event.metadata["revision"] == initial_revision + 1


def test_ready_import_is_placed_once_without_moving_existing_group():
    user, customer, project = create_customer_scope(email="auto-source@example.com")
    asset_a, version_a = attach_png_asset(
        customer=customer, project=project, user=user, name="already.png"
    )
    asset_b, _version_b = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        name="new.png",
        width_mm="30.00",
        height_mm="20.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Placement initial")
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset_a,
        added_by=user,
        width_mm="40.00",
        height_mm="20.00",
    )
    awaited = GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset_b,
        added_by=user,
        width_mm="30.00",
        height_mm="20.00",
        auto_placement_status=GangSheetSourceAsset.AutoPlacementStatus.AWAITING_ANALYSIS,
        sort_order=2,
    )
    existing = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version_a.public_id, actor=user
    )
    group_id = uuid4()
    existing.x_mm = Decimal("12.00")
    existing.y_mm = Decimal("14.00")
    existing.layout_group_id = group_id
    existing.save(update_fields=["x_mm", "y_mm", "layout_group_id", "updated_at"])
    sheet.refresh_from_db()

    updated, created, no_space = service.auto_place_ready_sources(
        sheet=sheet,
        expected_revision=sheet.revision,
        actor=user,
        source="test",
    )

    existing.refresh_from_db()
    awaited.refresh_from_db()
    assert len(created) == 1
    assert no_space == 0
    assert (existing.x_mm, existing.y_mm, existing.layout_group_id) == (
        Decimal("12.00"),
        Decimal("14.00"),
        group_id,
    )
    assert awaited.auto_placement_status == GangSheetSourceAsset.AutoPlacementStatus.PLACED
    assert service.geometry.issues(sheet=updated, items=list(updated.items.all())) == []
    placed_event_count = AuditLogEntry.objects.filter(
        action="gang_sheet.source_auto_placed"
    ).count()

    updated.refresh_from_db()
    _updated, repeated, repeated_no_space = service.auto_place_ready_sources(
        sheet=updated,
        expected_revision=updated.revision,
        actor=user,
        source="test",
    )
    assert repeated == []
    assert repeated_no_space == 0
    assert updated.items.count() == 2
    assert (
        AuditLogEntry.objects.filter(action="gang_sheet.source_auto_placed").count()
        == placed_event_count
    )


def test_ready_import_no_space_is_terminal_and_does_not_change_revision():
    user, customer, project = create_customer_scope(email="auto-no-space@example.com")
    asset, _version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Sans place")
    source = GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="600.00",
        height_mm="600.00",
        auto_placement_status=GangSheetSourceAsset.AutoPlacementStatus.AWAITING_ANALYSIS,
    )
    initial_revision = sheet.revision

    updated, created, no_space = service.auto_place_ready_sources(
        sheet=sheet,
        expected_revision=sheet.revision,
        actor=user,
        source="test",
    )

    source.refresh_from_db()
    assert created == []
    assert no_space == 1
    assert updated.revision == initial_revision
    assert updated.items.count() == 0
    assert source.auto_placement_status == GangSheetSourceAsset.AutoPlacementStatus.NO_SPACE
    with pytest.raises(GangSheetDomainError) as blocked:
        service.request_render(sheet=updated, actor=user, source="test")
    assert blocked.value.code == "AUTO_PLACEMENT_PENDING"


def test_existing_source_auto_crop_reads_current_private_file_and_ignores_client_crop():
    user, customer, project = create_customer_scope(email="crop-existing-auto@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    expected_content = version.file.read()
    version.file.close()
    detected_crop = CropBox.from_values(x="0.15", y="0.10", width="0.70", height="0.80")

    class RecordingAutoCrop:
        def detect(self, uploaded_file):
            assert uploaded_file.name == version.original_filename
            assert uploaded_file.content_type == version.mime_type
            assert uploaded_file.read() == expected_content
            return AutoCropResult(
                crop=detected_crop,
                content_kind="raster",
                basis="visible_pixels",
            )

    service = GangSheetService(auto_crop=RecordingAutoCrop())
    sheet = service.create_sheet(project=project, actor=user, name="Crop auto existant")
    source_asset = sheet.source_assets.get(asset=asset)

    updated_sheet, updated_source = service.update_source_asset_crop(
        sheet=sheet,
        source_asset_public_id=source_asset.public_id,
        crop=CropBox.full(),
        crop_mode="auto",
        expected_revision=sheet.revision,
        actor=user,
        source="test",
    )

    updated_source.refresh_from_db()
    assert CropBox.from_source_asset(updated_source) == detected_crop
    assert updated_sheet.revision == sheet.revision + 1
    event = AuditLogEntry.objects.get(action="gang_sheet.source_crop_updated")
    assert event.metadata["crop_mode"] == "auto"
    assert event.metadata["auto_crop"] == {
        "content_kind": "raster",
        "basis": "visible_pixels",
        "crop": detected_crop.to_metadata(),
    }


def test_existing_source_crop_rejects_invalid_crop_stale_revision_and_locked_sheet():
    user, customer, project = create_customer_scope(email="crop-guards@example.com")
    asset, _version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Crop protégé")
    source_asset = sheet.source_assets.get(asset=asset)
    invalid_crop = CropBox(
        x=Decimal("0.80"),
        y=Decimal("0"),
        width=Decimal("0.40"),
        height=Decimal("1"),
    )

    with pytest.raises(GangSheetDomainError) as invalid:
        service.update_source_asset_crop(
            sheet=sheet,
            source_asset_public_id=source_asset.public_id,
            crop=invalid_crop,
            expected_revision=sheet.revision,
            actor=user,
        )
    assert invalid.value.code == "INVALID_CROP"

    with pytest.raises(GangSheetDomainError) as stale:
        service.update_source_asset_crop(
            sheet=sheet,
            source_asset_public_id=source_asset.public_id,
            crop=CropBox.from_values(width="0.80"),
            expected_revision=sheet.revision + 1,
            actor=user,
        )
    assert stale.value.code == "STALE_REVISION"

    sheet.status = GangSheet.Status.VALIDATED
    sheet.save(update_fields=["status", "updated_at"])
    with pytest.raises(GangSheetDomainError) as locked:
        service.update_source_asset_crop(
            sheet=sheet,
            source_asset_public_id=source_asset.public_id,
            crop=CropBox.from_values(width="0.80"),
            expected_revision=sheet.revision,
            actor=user,
        )
    assert locked.value.code == "SHEET_LOCKED"
    source_asset.refresh_from_db()
    assert source_asset.has_crop is False


def test_existing_source_crop_cannot_target_another_customer_source_uuid():
    user_a, customer_a, project_a = create_customer_scope(email="crop-scope-a@example.com")
    asset_a, _version_a = attach_png_asset(
        customer=customer_a,
        project=project_a,
        user=user_a,
    )
    user_b, customer_b, project_b = create_customer_scope(email="crop-scope-b@example.com")
    attach_png_asset(customer=customer_b, project=project_b, user=user_b)
    service = GangSheetService()
    sheet_a = service.create_sheet(project=project_a, actor=user_a, name="Planche A")
    sheet_b = service.create_sheet(project=project_b, actor=user_b, name="Planche B")
    foreign_source = sheet_a.source_assets.get(asset=asset_a)

    with pytest.raises(GangSheetDomainError) as error:
        service.update_source_asset_crop(
            sheet=sheet_b,
            source_asset_public_id=foreign_source.public_id,
            crop=CropBox.from_values(width="0.80"),
            expected_revision=sheet_b.revision,
            actor=user_b,
        )

    assert error.value.code == "SOURCE_ASSET_NOT_FOUND"
    foreign_source.refresh_from_db()
    assert foreign_source.has_crop is False


def test_existing_source_crop_resizes_placed_visual_without_distorting_it():
    user, customer, project = create_customer_scope(email="crop-used@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Crop utilisé")
    source_asset = sheet.source_assets.get(asset=asset)
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    sheet.refresh_from_db()

    updated, _source = service.update_source_asset_crop(
        sheet=sheet,
        source_asset_public_id=source_asset.public_id,
        crop=CropBox.from_values(width="0.80"),
        expected_revision=sheet.revision,
        actor=user,
    )

    source_asset.refresh_from_db()
    item = updated.items.get()
    assert source_asset.has_crop is True
    assert item.width_mm == Decimal("80.00")
    assert item.height_mm == Decimal("50.00")
    event = AuditLogEntry.objects.get(action="gang_sheet.source_crop_updated")
    assert event.metadata["updated_occurrence_count"] == 1


def test_existing_source_crop_rolls_back_when_expansion_would_overlap():
    user, customer, project = create_customer_scope(email="crop-overlap@example.com")
    asset_a, version_a = attach_png_asset(
        customer=customer, project=project, user=user, name="crop-a.png"
    )
    asset_b, version_b = attach_png_asset(
        customer=customer, project=project, user=user, name="crop-b.png"
    )
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Crop collision")
    source_a = GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset_a,
        width_mm="100.00",
        height_mm="50.00",
        crop_width="0.500000",
    )
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset_b,
        width_mm="50.00",
        height_mm="50.00",
        sort_order=2,
    )
    first = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version_a.public_id, actor=user
    )
    sheet.refresh_from_db()
    second = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version_b.public_id, actor=user
    )
    first.x_mm, first.y_mm = Decimal("0"), Decimal("0")
    second.x_mm, second.y_mm = Decimal("55"), Decimal("0")
    first.save(update_fields=["x_mm", "y_mm", "updated_at"])
    second.save(update_fields=["x_mm", "y_mm", "updated_at"])
    sheet.refresh_from_db()

    with pytest.raises(GangSheetDomainError) as conflict:
        service.update_source_asset_crop(
            sheet=sheet,
            source_asset_public_id=source_a.public_id,
            crop=CropBox.full(),
            expected_revision=sheet.revision,
            actor=user,
        )

    assert conflict.value.code == "CROP_LAYOUT_CONFLICT"
    source_a.refresh_from_db()
    first.refresh_from_db()
    assert source_a.crop_width == Decimal("0.500000")
    assert first.width_mm == Decimal("50.00")


def test_draft_sheet_deletion_removes_composition_and_renders_but_preserves_sources(
    django_capture_on_commit_callbacks,
):
    user, customer, project = create_customer_scope(email="delete-sheet@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="À supprimer")
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    sheet.preview_file = SimpleUploadedFile("preview.png", b"preview", content_type="image/png")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
    )
    sheet.save(update_fields=["preview_file", "final_file", "updated_at"])
    sheet_pk = sheet.pk
    sheet_public_id = sheet.public_id
    preview_storage = sheet.preview_file.storage
    preview_name = sheet.preview_file.name
    final_storage = sheet.final_file.storage
    final_name = sheet.final_file.name

    with django_capture_on_commit_callbacks(execute=True):
        service.delete_sheet(sheet=sheet, actor=user, source="test")

    assert not GangSheet.objects.filter(pk=sheet_pk).exists()
    assert not GangSheetItem.objects.filter(sheet_id=sheet_pk).exists()
    assert not GangSheetSourceAsset.objects.filter(sheet_id=sheet_pk).exists()
    assert Asset.objects.filter(pk=asset.pk, is_archived=False).exists()
    assert not preview_storage.exists(preview_name)
    assert not final_storage.exists(final_name)
    event = AuditLogEntry.objects.get(
        action="gang_sheet.deleted",
        target_public_id=sheet_public_id,
    )
    assert event.metadata["name"] == "À supprimer"
    assert event.metadata["item_count"] == 1
    assert event.metadata["source_asset_count"] == 1


@pytest.mark.parametrize("status", [GangSheet.Status.RENDERING, GangSheet.Status.VALIDATED])
def test_rendering_or_validated_sheet_cannot_be_deleted(status):
    user, customer, _project = create_customer_scope(email=f"blocked-{status}@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Traçable")
    sheet.status = status
    sheet.save(update_fields=["status", "updated_at"])

    with pytest.raises(GangSheetDomainError) as exc:
        service.delete_sheet(sheet=sheet, actor=user, source="test")

    assert exc.value.code == "SHEET_NOT_DELETABLE"
    assert GangSheet.objects.filter(pk=sheet.pk).exists()


def test_sheet_linked_to_an_order_project_cannot_be_deleted():
    user, _customer, project = create_customer_scope(email="linked-delete@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Liée")

    with pytest.raises(GangSheetDomainError) as exc:
        service.delete_sheet(sheet=sheet, actor=user, source="test")

    assert exc.value.code == "SHEET_NOT_DELETABLE"
    assert GangSheet.objects.filter(pk=sheet.pk).exists()


def test_unused_visual_can_be_removed_from_gallery_without_deleting_source_file():
    user, customer, project = create_customer_scope(email="remove-gallery@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Galerie modifiable")
    source_asset = GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    source_file_name = version.file.name
    source_storage = version.file.storage

    removed_name = service.remove_source_asset(
        sheet=sheet,
        source_asset_public_id=source_asset.public_id,
        actor=user,
        source="test",
    )

    assert removed_name == asset.name
    assert not GangSheetSourceAsset.objects.filter(pk=source_asset.pk).exists()
    assert Asset.objects.filter(pk=asset.pk, current_version=version).exists()
    assert source_storage.exists(source_file_name)
    event = AuditLogEntry.objects.get(action="gang_sheet.source_removed")
    assert event.target_public_id == sheet.public_id
    assert event.metadata["asset_public_id"] == str(asset.public_id)
    assert event.metadata["source_file_preserved"] is True


def test_visual_used_in_composition_cannot_be_removed_from_gallery():
    user, customer, project = create_customer_scope(email="remove-used-gallery@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Galerie utilisée")
    source_asset = GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )

    with pytest.raises(GangSheetDomainError) as exc:
        service.remove_source_asset(
            sheet=sheet,
            source_asset_public_id=source_asset.public_id,
            actor=user,
            source="test",
        )

    assert exc.value.code == "SOURCE_ASSET_IN_USE"
    assert exc.value.details["usage_count"] == 1
    assert GangSheetSourceAsset.objects.filter(pk=source_asset.pk).exists()


def test_transformed_sheet_can_be_deleted_while_order_project_and_hd_files_are_preserved(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    user, customer, _project = create_customer_scope(email="delete-converted-sheet@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Commande conservée")
    production_pdf = b"%PDF-1.4\n% production preserved\n%%EOF\n"
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        production_pdf,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )
    project = service.create_order_project(sheet=sheet, actor=user, source="test")
    item = project.items.select_related("asset__current_version").get()
    production_asset = item.asset
    production_version = production_asset.current_version
    order = Order.objects.create(customer=customer, created_by=user)
    order_upload = OrderUpload.objects.create(
        order=order,
        uploaded_by=user,
        asset_version=production_version,
        file=SimpleUploadedFile(
            "production-order.pdf",
            production_pdf,
            content_type="application/pdf",
        ),
        original_filename="production-order.pdf",
        mime_type="application/pdf",
        size_bytes=len(production_pdf),
        quantity=1,
        width_mm=sheet.width_mm,
        height_mm=sheet.height_mm,
    )
    project.status = B2BOrderProject.Status.CONVERTED
    project.converted_order = order
    project.save(update_fields=["status", "converted_order", "updated_at"])
    sheet.refresh_from_db()
    sheet.order = order
    sheet.save(update_fields=["order", "updated_at"])
    sheet = mark_gang_sheet_drive_synced(sheet)
    sheet_pk = sheet.pk
    sheet_public_id = sheet.public_id

    assert service.can_client_delete(sheet) is True
    with django_capture_on_commit_callbacks(execute=True):
        service.delete_sheet(sheet=sheet, actor=user, source="test")

    assert not GangSheet.objects.filter(pk=sheet_pk).exists()
    assert B2BOrderProject.objects.filter(pk=project.pk, converted_order=order).exists()
    assert Order.objects.filter(pk=order.pk).exists()
    assert Asset.objects.filter(pk=production_asset.pk, current_version=production_version).exists()
    assert OrderUpload.objects.filter(pk=order_upload.pk, asset_version=production_version).exists()
    production_version.file.open("rb")
    try:
        assert production_version.file.read() == production_pdf
    finally:
        production_version.file.close()
    order_upload.file.open("rb")
    try:
        assert order_upload.file.read() == production_pdf
    finally:
        order_upload.file.close()
    item.refresh_from_db()
    assert B2BOrderProjectService._is_production_item(item) is True
    event = AuditLogEntry.objects.get(
        action="gang_sheet.deleted",
        target_public_id=sheet_public_id,
    )
    assert event.metadata["order_preserved"] is True
    assert event.metadata["project_preserved"] is True
    assert event.metadata["production_asset_preserved"] is True


def test_sheet_can_be_deleted_once_hd_is_secured_in_ready_gang_sheet_project_before_checkout(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    user, customer, _project = create_customer_scope(email="delete-ready-project@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Projet prêt")
    production_pdf = b"%PDF-1.4\n% secured in project\n%%EOF\n"
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        production_pdf,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )
    project = service.create_order_project(sheet=sheet, actor=user, source="test")
    item = project.items.select_related("asset__current_version").get()
    production_asset = item.asset
    production_version = production_asset.current_version
    sheet.refresh_from_db()
    sheet = mark_gang_sheet_drive_synced(sheet)

    assert sheet.order_id is None
    assert project.order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET
    assert service.can_client_delete(sheet) is True
    with django_capture_on_commit_callbacks(execute=True):
        service.delete_sheet(sheet=sheet, actor=user, source="test")

    assert not GangSheet.objects.filter(pk=sheet.pk).exists()
    assert B2BOrderProject.objects.filter(pk=project.pk, converted_order__isnull=True).exists()
    assert Asset.objects.filter(pk=production_asset.pk, current_version=production_version).exists()
    production_version.file.open("rb")
    try:
        assert production_version.file.read() == production_pdf
    finally:
        production_version.file.close()
    item.refresh_from_db()
    assert B2BOrderProjectService._is_production_item(item) is True


@override_settings(GOOGLE_DRIVE_SYNC_ENABLED=True)
def test_ready_project_sheet_remains_protected_until_current_hd_revision_is_synced_to_drive(
    monkeypatch,
):
    user, customer, _project = create_customer_scope(email="delete-drive-guard@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Drive requis")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        b"%PDF-1.4\n%%EOF\n",
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )
    service.create_order_project(sheet=sheet, actor=user, source="test")
    sheet.refresh_from_db()

    assert service.can_client_delete(sheet) is False

    GangSheetDriveSync.objects.create(
        customer=customer,
        gang_sheet=sheet,
        status=GangSheetDriveSync.Status.SYNCED,
        revision=sheet.revision,
        drive_filename="production.pdf",
        drive_file_id="drive-file-current-revision",
    )
    sheet.refresh_from_db()

    assert service.can_client_delete(sheet) is True


def test_standalone_upload_is_analyzed_and_populates_gallery_dimensions(monkeypatch):
    user, customer, _project = create_customer_scope(email="upload-standalone@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Galerie")
    _asset, source_version = attach_png_asset(
        customer=customer,
        project=_project,
        user=user,
        name="source.png",
    )
    source_version.file.open("rb")
    uploaded = SimpleUploadedFile(
        "nouveau.png",
        source_version.file.read(),
        content_type="image/png",
    )
    source_version.file.close()
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )

    entry, version = GangSheetService().upload_source_asset(
        sheet=sheet,
        actor=user,
        uploaded_file=uploaded,
    )
    analyzed = AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")

    entry.refresh_from_db()
    assert analyzed.analysis_status in {
        AssetVersion.AnalysisStatus.READY,
        AssetVersion.AnalysisStatus.WARNING,
    }
    assert entry.width_mm is not None
    assert entry.height_mm is not None
    assert list(GangSheetService().available_asset_versions(sheet=sheet)) == [analyzed]


def test_validated_standalone_sheet_creates_one_idempotent_ready_gang_sheet_project(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    user, customer, _project = create_customer_scope(email="convert-standalone@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Commande finale")
    production_pdf = b"%PDF-1.4\n% HD gang sheet payload\n%%EOF\n"
    sheet.status = GangSheet.Status.VALIDATED
    sheet.final_file = SimpleUploadedFile(
        "production.pdf",
        production_pdf,
        content_type="application/pdf",
    )
    sheet.save(update_fields=["status", "final_file", "updated_at"])

    scheduled_versions = []
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: scheduled_versions.append(version.public_id),
    )
    service = GangSheetService()

    with django_capture_on_commit_callbacks(execute=True):
        project = service.create_order_project(sheet=sheet, actor=user)
    same_project = service.create_order_project(sheet=sheet, actor=user)

    sheet.refresh_from_db()
    item = project.items.get()
    version = item.asset.current_version
    assert same_project == project
    assert project.order_mode == B2BOrderProject.OrderMode.READY_GANG_SHEET
    assert project.status == B2BOrderProject.Status.INCOMPLETE
    assert project.items.count() == 1
    assert item.quantity == 1
    assert item.width_mm == sheet.width_mm
    assert item.height_mm == sheet.height_mm
    assert item.asset == sheet.production_asset
    assert item.client_confirmed_asset_version is None
    assert version.analysis_status == AssetVersion.AnalysisStatus.PENDING
    assert version.sha256 == hashlib.sha256(production_pdf).hexdigest()
    assert AssetAnalysis.objects.filter(version=version).exists() is False
    assert scheduled_versions == [version.public_id]
    version.file.open("rb")
    try:
        assert version.file.read() == production_pdf
    finally:
        version.file.close()
    production_audit = AuditLogEntry.objects.filter(action="asset.created").latest("created_at")
    assert production_audit.metadata["production_output"] is True
    assert GangSheetSourceAsset.objects.filter(sheet=sheet, asset=item.asset).exists() is False
    with pytest.raises(ProjectDomainError, match="verrouillé"):
        B2BOrderProjectService().delete_item(
            project=project,
            item_public_id=item.public_id,
            actor=user,
            source="test",
        )
    with pytest.raises(ProjectDomainError, match="uniquement"):
        B2BOrderProjectService().add_item(
            project=project,
            actor=user,
            data={
                "name": "Intrus",
                "width_mm": "10",
                "height_mm": "10",
                "quantity": 1,
            },
            source="test",
        )


def test_sheet_snapshots_workshop_width_and_calculates_live_price():
    user, customer, project = create_customer_scope(email="owner@example.com")
    config = GangSheetSiteSettings.current()
    config.roll_width_mm = Decimal("570.00")
    config.minimum_height_mm = Decimal("120.00")
    config.item_spacing_mm = Decimal("4.50")
    config.save()

    sheet = GangSheetService().create_sheet(project=project, actor=user, name="Série A")

    assert sheet.width_mm == Decimal("570.00")
    assert sheet.height_mm == Decimal("120.00")
    assert sheet.item_spacing_x_mm == Decimal("4.50")
    assert sheet.item_spacing_y_mm == Decimal("4.50")
    assert sheet.surface_sqm == Decimal("0.0684")
    assert sheet.unit_price_eur == Decimal("25.00")
    assert sheet.estimated_price_eur == Decimal("1.71")

    config.roll_width_mm = Decimal("550.00")
    config.save()
    sheet.refresh_from_db()
    assert sheet.width_mm == Decimal("570.00")


def test_workshop_settings_hide_the_legacy_margin_without_overwriting_it():
    config = GangSheetSiteSettings.current()
    config.margin_mm = Decimal("100.00")
    config.save(update_fields=["margin_mm", "updated_at"])
    form = GangSheetSiteSettingsForm(
        data={
            "roll_width_mm": "100.00",
            "item_spacing_mm": "3.00",
            "minimum_height_mm": "100.00",
            "maximum_height_mm": "2000.00",
            "height_step_mm": "10.00",
        },
        instance=config,
    )

    assert "margin_mm" not in form.fields
    assert form.is_valid(), form.errors
    saved = form.save()
    assert saved.roll_width_mm == Decimal("100.00")
    assert saved.margin_mm == Decimal("100.00")


def test_django_admin_hides_the_legacy_margin_setting():
    model_admin = admin.site._registry[GangSheetSiteSettings]

    assert "margin_mm" in model_admin.exclude


def test_required_height_and_initial_origin_ignore_the_legacy_margin():
    user, customer, project = create_customer_scope(email="legacy-margin@example.com")
    config = GangSheetSiteSettings.current()
    config.margin_mm = Decimal("37.00")
    config.save(update_fields=["margin_mm", "updated_at"])
    _asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="100.00",
        height_mm="100.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Marge historique")

    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()

    assert item.x_mm == Decimal("0.00")
    assert item.y_mm == Decimal("0.00")
    assert sheet.height_mm == Decimal("100.00")


def test_occurrences_auto_place_without_overlap_and_height_is_automatic():
    user, customer, project = create_customer_scope(email="layout@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Compacte")
    first = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()
    second = service.duplicate_occurrence(
        sheet=sheet,
        item_public_id=first.public_id,
        expected_revision=sheet.revision,
        actor=user,
    )

    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)
    sheet.refresh_from_db()
    items = list(sheet.items.all())

    assert {item.public_id for item in items} == {first.public_id, second.public_id}
    assert GangSheetGeometryService().issues(sheet=sheet, items=items) == []
    assert sheet.height_mm >= Decimal("60.00")
    assert sheet.surface_sqm > 0


def test_delete_occurrences_removes_the_exact_selection_atomically_and_audits_it():
    user, customer, project = create_customer_scope(email="batch-delete-service@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Suppression groupée")
    items = service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=3,
        actor=user,
    )
    sheet.refresh_from_db()
    initial_revision = sheet.revision

    deleted_count = service.delete_occurrences(
        sheet=sheet,
        item_public_ids=[items[0].public_id, items[2].public_id, items[0].public_id],
        actor=user,
    )

    sheet.refresh_from_db()
    remaining = list(sheet.items.all())
    audit = AuditLogEntry.objects.get(action="gang_sheet.items_batch_deleted")
    assert deleted_count == 2
    assert [item.public_id for item in remaining] == [items[1].public_id]
    assert remaining[0].z_index == 1
    assert sheet.revision == initial_revision + 1
    assert audit.metadata["item_count"] == 2
    assert set(audit.metadata["item_public_ids"]) == {
        str(items[0].public_id),
        str(items[2].public_id),
    }


def test_delete_occurrences_rolls_back_when_one_selected_item_is_missing():
    user, customer, project = create_customer_scope(email="batch-delete-atomic@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Suppression atomique")
    items = service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=2,
        actor=user,
    )

    with pytest.raises(GangSheetDomainError) as exc:
        service.delete_occurrences(
            sheet=sheet,
            item_public_ids=[items[0].public_id, "00000000-0000-0000-0000-000000000000"],
            actor=user,
        )

    assert exc.value.code == "ITEM_NOT_FOUND"
    assert set(sheet.items.values_list("public_id", flat=True)) == {
        items[0].public_id,
        items[1].public_id,
    }

    sheet.status = GangSheet.Status.VALIDATED
    sheet.save(update_fields=["status", "updated_at"])
    with pytest.raises(GangSheetDomainError) as locked_exc:
        service.delete_occurrences(
            sheet=sheet,
            item_public_ids=[items[0].public_id, items[1].public_id],
            actor=user,
        )

    assert locked_exc.value.code == "SHEET_LOCKED"
    assert sheet.items.count() == 2


def test_delete_occurrences_rejects_items_from_another_sheet_or_tenant_atomically():
    user, customer, project = create_customer_scope(email="batch-delete-boundary@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Planche autorisée")
    selected_item = service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    same_tenant_sheet = service.create_sheet(
        project=project,
        actor=user,
        name="Autre planche du client",
    )
    same_tenant_item = service.add_occurrence(
        sheet=same_tenant_sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    other_user, other_customer, other_project = create_customer_scope(
        email="batch-delete-other-tenant@example.com"
    )
    _other_asset, other_version = attach_png_asset(
        customer=other_customer,
        project=other_project,
        user=other_user,
    )
    other_sheet = service.create_sheet(
        project=other_project,
        actor=other_user,
        name="Planche d'un autre client",
    )
    other_tenant_item = service.add_occurrence(
        sheet=other_sheet,
        asset_version_public_id=other_version.public_id,
        actor=other_user,
    )
    sheet.refresh_from_db()
    initial_revision = sheet.revision

    for foreign_item in (same_tenant_item, other_tenant_item):
        with pytest.raises(GangSheetDomainError) as exc:
            service.delete_occurrences(
                sheet=sheet,
                item_public_ids=[selected_item.public_id, foreign_item.public_id],
                actor=user,
            )

        assert exc.value.code == "ITEM_NOT_FOUND"
        sheet.refresh_from_db()
        assert sheet.revision == initial_revision
        assert sheet.items.filter(public_id=selected_item.public_id).exists()
        assert foreign_item.__class__.objects.filter(pk=foreign_item.pk).exists()
        assert not AuditLogEntry.objects.filter(
            action="gang_sheet.items_batch_deleted",
            target_public_id=sheet.public_id,
        ).exists()


def test_delete_occurrences_rollback_preserves_derived_files_and_database(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    user, customer, project = create_customer_scope(email="batch-delete-file-rollback@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Rendu à préserver")
    items = service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=2,
        actor=user,
    )
    sheet.status = GangSheet.Status.READY
    sheet.preview_file = SimpleUploadedFile("preview.png", b"preview", content_type="image/png")
    sheet.final_file = SimpleUploadedFile(
        "production.pdf", b"%PDF-1.4\n%%EOF\n", content_type="application/pdf"
    )
    sheet.save(update_fields=["status", "preview_file", "final_file", "updated_at"])
    sheet.refresh_from_db()
    initial_revision = sheet.revision
    preview_storage = sheet.preview_file.storage
    preview_name = sheet.preview_file.name
    final_storage = sheet.final_file.storage
    final_name = sheet.final_file.name

    def fail_after_mark_dirty(_sheet):
        raise RuntimeError("forced refresh failure")

    monkeypatch.setattr(service, "_refresh_sheet", fail_after_mark_dirty)

    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError, match="forced refresh failure"):
            service.delete_occurrences(
                sheet=sheet,
                item_public_ids=[item.public_id for item in items],
                actor=user,
            )

    sheet.refresh_from_db()
    assert callbacks == []
    assert sheet.revision == initial_revision
    assert sheet.status == GangSheet.Status.READY
    assert sheet.preview_file.name == preview_name
    assert sheet.final_file.name == final_name
    assert preview_storage.exists(preview_name)
    assert final_storage.exists(final_name)
    assert sheet.items.count() == 2
    assert not AuditLogEntry.objects.filter(
        action="gang_sheet.items_batch_deleted",
        target_public_id=sheet.public_id,
    ).exists()


def test_auto_place_persists_and_applies_axis_specific_spacing():
    user, customer, project = create_customer_scope(email="axis-spacing@example.com")
    _asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="100.00",
        height_mm="100.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Espacement XY")
    service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=2,
        actor=user,
    )

    service.auto_place(
        sheet=sheet,
        actor=user,
        spacing_x_mm="7.25",
        spacing_y_mm="11.50",
    )

    sheet.refresh_from_db()
    items = sorted(sheet.items.all(), key=lambda item: (item.y_mm, item.x_mm))
    assert sheet.item_spacing_x_mm == Decimal("7.25")
    assert sheet.item_spacing_y_mm == Decimal("11.50")
    assert items[1].x_mm - items[0].effective_width_mm - items[0].x_mm == Decimal("7.25")
    assert items[1].y_mm == items[0].y_mm
    assert GangSheetGeometryService().issues(sheet=sheet, items=items) == []


def test_auto_place_applies_vertical_spacing_when_a_new_column_does_not_fit():
    user, customer, project = create_customer_scope(email="vertical-spacing@example.com")
    _asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="272.00",
        height_mm="272.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Espacement vertical")
    service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=2,
        actor=user,
    )

    service.auto_place(
        sheet=sheet,
        actor=user,
        spacing_x_mm="7.25",
        spacing_y_mm="11.50",
    )

    items = sorted(sheet.items.all(), key=lambda item: (item.y_mm, item.x_mm))
    assert items[1].y_mm - items[0].effective_height_mm - items[0].y_mm == Decimal("11.50")
    assert items[1].x_mm == items[0].x_mm


def test_batch_quantity_creates_and_places_every_occurrence_atomically():
    user, customer, project = create_customer_scope(email="batch@example.com")
    _asset, version = attach_png_asset(
        customer=customer, project=project, user=user, width_mm="80.00", height_mm="40.00"
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Série de cinq")

    created = service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=5,
        auto_place=True,
        actor=user,
    )

    sheet.refresh_from_db()
    items = list(sheet.items.all())
    assert len(created) == 5
    assert len(items) == 5
    assert GangSheetGeometryService().issues(sheet=sheet, items=items) == []
    assert sheet.revision == 2


def test_batch_quantity_limit_rolls_back_without_partial_occurrences():
    user, customer, project = create_customer_scope(email="batch-limit@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Limite")

    with pytest.raises(GangSheetDomainError) as exc:
        service.add_occurrences(
            sheet=sheet,
            asset_version_public_id=version.public_id,
            quantity=201,
            auto_place=True,
            actor=user,
        )

    assert exc.value.code == "BATCH_LIMIT_EXCEEDED"
    assert sheet.items.count() == 0


def test_selected_occurrence_can_generate_regular_rows_and_columns():
    user, customer, project = create_customer_scope(email="grid@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Grille")
    source = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )

    service.repeat_occurrence_grid(
        sheet=sheet,
        item_public_id=source.public_id,
        rows=2,
        columns=3,
        spacing_x_mm="3.00",
        spacing_y_mm="3.00",
        actor=user,
    )

    sheet.refresh_from_db()
    items = list(sheet.items.all())
    positions = {(item.x_mm, item.y_mm) for item in items}
    assert len(items) == 6
    assert positions == {
        (Decimal("0.00"), Decimal("0.00")),
        (Decimal("103.00"), Decimal("0.00")),
        (Decimal("206.00"), Decimal("0.00")),
        (Decimal("0.00"), Decimal("53.00")),
        (Decimal("103.00"), Decimal("53.00")),
        (Decimal("206.00"), Decimal("53.00")),
    }
    assert GangSheetGeometryService().issues(sheet=sheet, items=items) == []


def test_grid_rejects_a_true_overflow_of_the_useful_width():
    user, customer, project = create_customer_scope(email="grid-margin@example.com")
    _asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="281.00",
        height_mm="40.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Grille et marge")
    source = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()
    initial_revision = sheet.revision

    with pytest.raises(GangSheetDomainError) as exc:
        service.repeat_occurrence_grid(
            sheet=sheet,
            item_public_id=source.public_id,
            rows=1,
            columns=2,
            spacing_x_mm="0",
            spacing_y_mm="0",
            actor=user,
        )

    assert exc.value.code == "GRID_TOO_LARGE"
    sheet.refresh_from_db()
    assert sheet.items.count() == 1
    assert sheet.revision == initial_revision


def test_grid_accepts_exact_useful_width_and_maximum_height():
    user, customer, project = create_customer_scope(email="grid-exact-bounds@example.com")
    _asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="275.00",
        height_mm="100.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Grille aux limites")
    source = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )

    service.repeat_occurrence_grid(
        sheet=sheet,
        item_public_id=source.public_id,
        rows=20,
        columns=2,
        spacing_x_mm="0",
        spacing_y_mm="0",
        actor=user,
    )

    sheet.refresh_from_db()
    rects = [service.geometry.rect_for(item) for item in sheet.items.all()]
    assert max(rect.right for rect in rects) == sheet.width_mm
    assert max(rect.bottom for rect in rects) == sheet.maximum_height_mm
    assert service.geometry.issues(sheet=sheet, items=list(sheet.items.all())) == []


def test_cross_tenant_asset_is_rejected_even_with_public_uuid():
    user, _customer, project = create_customer_scope(email="first@example.com")
    other_user, other_customer, other_project = create_customer_scope(email="other@example.com")
    _asset, other_version = attach_png_asset(
        customer=other_customer, project=other_project, user=other_user
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Privée")

    with pytest.raises(GangSheetDomainError, match="pas rattaché") as exc:
        service.add_occurrence(
            sheet=sheet,
            asset_version_public_id=other_version.public_id,
            actor=user,
        )

    assert exc.value.code == "ASSET_NOT_AVAILABLE"
    assert sheet.items.count() == 0


def test_stale_revision_cannot_overwrite_a_newer_draft():
    user, customer, project = create_customer_scope(email="revision@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Versionnée")
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()

    with pytest.raises(GangSheetDomainError) as exc:
        service.save_layout(
            sheet=sheet,
            expected_revision=sheet.revision - 1,
            payload=[
                {
                    "public_id": str(item.public_id),
                    "x_mm": "5",
                    "y_mm": "5",
                    "width_mm": "100",
                    "height_mm": "50",
                    "rotation": 0,
                }
            ],
            actor=user,
        )

    assert exc.value.code == "STALE_REVISION"


@pytest.mark.parametrize("revision", [None, True, "invalid", "1.5"])
def test_save_layout_requires_an_explicit_integer_revision(revision):
    user, customer, project = create_customer_scope(email=f"revision-{revision}@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Révision obligatoire")
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()

    with pytest.raises(GangSheetDomainError) as exc:
        service.save_layout(
            sheet=sheet,
            expected_revision=revision,
            payload=[
                {
                    "public_id": str(item.public_id),
                    "x_mm": "5",
                    "y_mm": "5",
                    "width_mm": "100",
                    "height_mm": "50",
                    "rotation": 0,
                }
            ],
            actor=user,
        )

    assert exc.value.code == "INVALID_LAYOUT"


@pytest.mark.parametrize(
    ("rotation", "effective_width", "effective_height"),
    [
        (0, "100.00", "50.00"),
        (90, "50.00", "100.00"),
        (180, "100.00", "50.00"),
        (270, "50.00", "100.00"),
    ],
)
def test_geometry_accepts_exact_useful_edges_for_every_rotation(
    rotation, effective_width, effective_height
):
    user, customer, project = create_customer_scope(email=f"exact-edge-{rotation}@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Limites utiles")
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.height_mm = sheet.maximum_height_mm
    item.rotation = rotation
    item.x_mm = sheet.width_mm - Decimal(effective_width)
    item.y_mm = sheet.height_mm - Decimal(effective_height)

    assert service.geometry.issues(sheet=sheet, items=[item]) == []

    item.x_mm = Decimal("0.00")
    item.y_mm = Decimal("0.00")
    assert service.geometry.issues(sheet=sheet, items=[item]) == []


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("axis", ["right", "bottom"])
def test_geometry_rejects_a_point_zero_one_overflow_for_every_rotation(rotation, axis):
    user, customer, project = create_customer_scope(email=f"overflow-{rotation}-{axis}@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Dépassement réel")
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.height_mm = sheet.maximum_height_mm
    item.rotation = rotation
    effective_width = item.height_mm if rotation in {90, 270} else item.width_mm
    effective_height = item.width_mm if rotation in {90, 270} else item.height_mm
    item.x_mm = sheet.width_mm - effective_width
    item.y_mm = sheet.height_mm - effective_height
    if axis == "right":
        item.x_mm += Decimal("0.01")
    else:
        item.y_mm += Decimal("0.01")

    issues = service.geometry.issues(sheet=sheet, items=[item])
    assert [issue["code"] for issue in issues] == ["overflow"]


@pytest.mark.parametrize(("x_mm", "y_mm"), [("-0.01", "0"), ("0", "-0.01")])
def test_manual_layout_rejects_top_or_left_overflow(x_mm, y_mm):
    user, customer, project = create_customer_scope(email=f"negative-{x_mm}-{y_mm}@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Origine invalide")
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()

    with pytest.raises(GangSheetDomainError) as exc:
        service.save_layout(
            sheet=sheet,
            expected_revision=sheet.revision,
            payload=[
                {
                    "public_id": str(item.public_id),
                    "x_mm": x_mm,
                    "y_mm": y_mm,
                    "width_mm": "100",
                    "height_mm": "50",
                    "rotation": 0,
                }
            ],
            actor=user,
        )

    assert exc.value.code == "INVALID_LAYOUT"


def test_manual_layout_accepts_zero_origin_and_render_blocks_true_overflow():
    user, customer, project = create_customer_scope(email="manual-overflow@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Laize utile")
    item = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()

    saved, issues = service.save_layout(
        sheet=sheet,
        expected_revision=sheet.revision,
        payload=[
            {
                "public_id": str(item.public_id),
                "x_mm": "0",
                "y_mm": "0",
                "width_mm": "100",
                "height_mm": "50",
                "rotation": 0,
            }
        ],
        actor=user,
    )

    assert issues == []
    saved.items.filter(pk=item.pk).update(width_mm=saved.width_mm + Decimal("0.01"))
    with pytest.raises(GangSheetDomainError) as exc:
        service.request_render(sheet=saved, actor=user)
    assert exc.value.code == "INVALID_GEOMETRY"


def test_duplicate_uses_a_free_position_inside_the_useful_sheet():
    user, customer, project = create_customer_scope(email="duplicate-position@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Duplication sûre")
    source = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()

    duplicate = service.duplicate_occurrence(
        sheet=sheet,
        item_public_id=source.public_id,
        expected_revision=sheet.revision,
        actor=user,
    )
    sheet.refresh_from_db()

    assert duplicate.x_mm == source.x_mm + source.effective_width_mm + sheet.item_spacing_x_mm
    assert duplicate.y_mm == source.y_mm
    assert GangSheetGeometryService().issues(sheet=sheet, items=list(sheet.items.all())) == []


def test_duplicate_fails_atomically_when_no_free_position_exists():
    user, customer, project = create_customer_scope(email="duplicate-full@example.com")
    _asset, version = attach_png_asset(
        customer=customer,
        project=project,
        user=user,
        width_mm="560.00",
        height_mm="1990.00",
    )
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Planche pleine")
    source = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()
    initial_revision = sheet.revision

    with pytest.raises(GangSheetDomainError) as exc:
        service.duplicate_occurrence(
            sheet=sheet,
            item_public_id=source.public_id,
            expected_revision=sheet.revision,
            actor=user,
        )

    assert exc.value.code == "DUPLICATE_NO_SPACE"
    sheet.refresh_from_db()
    assert sheet.items.count() == 1
    assert sheet.revision == initial_revision


def test_duplicate_of_an_invalid_draft_item_is_placed_inside_the_useful_sheet():
    user, customer, project = create_customer_scope(email="duplicate-invalid-source@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Source hors marge")
    source = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.items.filter(pk=source.pk).update(x_mm="0", y_mm="0")
    source.refresh_from_db()
    sheet.refresh_from_db()

    duplicate = service.duplicate_occurrence(
        sheet=sheet,
        item_public_id=source.public_id,
        expected_revision=sheet.revision,
        actor=user,
    )
    duplicate.refresh_from_db()
    duplicate_rect = GangSheetGeometryService().rect_for(duplicate)

    assert duplicate_rect.x >= 0
    assert duplicate_rect.y >= 0
    assert duplicate_rect.right <= sheet.width_mm
    assert duplicate_rect.bottom <= sheet.maximum_height_mm


def test_auto_place_refuses_persisted_groups_without_mutating_the_sheet():
    user, customer, project = create_customer_scope(email="group-auto-place@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Groupe protégé")
    service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=2,
        actor=user,
    )
    group_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    sheet.items.update(layout_group_id=group_id)
    sheet.refresh_from_db()
    initial_revision = sheet.revision
    initial_positions = list(sheet.items.values_list("public_id", "x_mm", "y_mm"))

    with pytest.raises(GangSheetDomainError) as exc:
        service.auto_place(
            sheet=sheet,
            actor=user,
            spacing_x_mm="17",
            spacing_y_mm="19",
        )

    assert exc.value.code == "AUTO_PLACE_GROUPED_ITEMS"
    sheet.refresh_from_db()
    assert sheet.revision == initial_revision
    assert sheet.item_spacing_x_mm != Decimal("17")
    assert list(sheet.items.values_list("public_id", "x_mm", "y_mm")) == initial_positions
    assert {str(value) for value in sheet.items.values_list("layout_group_id", flat=True)} == {
        group_id
    }


def test_save_layout_persists_layout_group_id():
    user, customer, project = create_customer_scope(email="group-layout@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Groupée")
    first = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    second = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()
    group_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    locked, issues = service.save_layout(
        sheet=sheet,
        expected_revision=sheet.revision,
        payload=[
            {
                "public_id": str(first.public_id),
                "x_mm": "10",
                "y_mm": "10",
                "width_mm": "80",
                "height_mm": "40",
                "rotation": 0,
                "layout_group_id": group_id,
            },
            {
                "public_id": str(second.public_id),
                "x_mm": "100",
                "y_mm": "10",
                "width_mm": "80",
                "height_mm": "40",
                "rotation": 0,
                "layout_group_id": group_id,
            },
        ],
        actor=user,
    )

    first.refresh_from_db()
    second.refresh_from_db()
    assert str(first.layout_group_id) == group_id
    assert str(second.layout_group_id) == group_id
    serialized = service.serialize_sheet(locked, preview_url_resolver=lambda _version: "")
    assert {item["layout_group_id"] for item in serialized["items"]} == {group_id}
    assert issues == []


def test_request_render_locks_items_with_nullable_asset_version(
    monkeypatch,
    django_capture_on_commit_callbacks,
):
    user, customer, project = create_customer_scope(email="request-render@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Rendu demandé")
    service.add_occurrence(sheet=sheet, asset_version_public_id=version.public_id, actor=user)
    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)

    scheduled = []
    monkeypatch.setattr(
        "apps.gang_sheets.tasks.render_gang_sheet_task.delay",
        lambda sheet_public_id: scheduled.append(sheet_public_id),
    )

    with django_capture_on_commit_callbacks(execute=True):
        requested = service.request_render(sheet=sheet, actor=user, source="test")

    assert requested.status == GangSheet.Status.RENDERING
    assert scheduled == [str(sheet.public_id)]


def test_render_creates_low_resolution_preview_and_private_production_pdf():
    user, customer, project = create_customer_scope(email="render@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Production")
    service.add_occurrence(sheet=sheet, asset_version_public_id=version.public_id, actor=user)
    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)
    sheet.refresh_from_db()
    sheet.status = GangSheet.Status.RENDERING
    sheet.save(update_fields=["status", "updated_at"])

    rendered = GangSheetRenderService().render(sheet_public_id=sheet.public_id)

    assert rendered.status == GangSheet.Status.READY
    assert rendered.preview_file.name.endswith(".png")
    assert rendered.final_file.name.endswith(".pdf")
    rendered.final_file.open("rb")
    assert rendered.final_file.read(5) == b"%PDF-"
    rendered.final_file.close()


def test_generated_hd_pdf_keeps_quality_overlays_without_false_sheet_dpi(monkeypatch):
    user, customer, source_project = create_customer_scope(email="hd-quality@example.com")
    asset, version = attach_png_asset(
        customer=customer,
        project=source_project,
        user=user,
    )
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Contrôle HD")
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm="100.00",
        height_mm="50.00",
    )
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)
    sheet.refresh_from_db()
    sheet.status = GangSheet.Status.RENDERING
    sheet.save(update_fields=["status", "updated_at"])
    sheet = GangSheetRenderService().render(sheet_public_id=sheet.public_id)
    sheet = service.validate_sheet(sheet=sheet, actor=user)
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )

    project = service.create_order_project(sheet=sheet, actor=user, source="test")
    production_version = project.items.get().asset.current_version
    AssetAnalysisService().analyze(
        version_public_id=production_version.public_id,
        source="test",
    )
    item = project.items.select_related("asset__current_version__analysis").get()
    metadata = item.asset.current_version.analysis.metadata or {}
    raw_review = AssetService().technical_review_for_item(item=item)
    production_review = AssetService().production_review_for_item(item=item)

    # Motif 300×150 px sur ~100×50 mm → DPI placement réel (~76), pas le faux DPI page.
    assert metadata.get("placement_effective_dpi") is not None
    assert metadata.get("uses_artboard_dimensions") is False
    assert raw_review["effective_dpi"] == pytest.approx(
        float(metadata["placement_effective_dpi"]),
        rel=0.01,
    )
    assert production_review["label"] == "Contrôle du fichier HD"
    assert str(production_review["resolution_display"]).endswith("DPI")
    assert production_review["resolution_display"] != "PDF hybride"
    assert production_review["effective_dpi"] == pytest.approx(
        float(metadata["placement_effective_dpi"]),
        rel=0.01,
    )
    assert production_review["can_confirm"] is True
    assert "thin_zone" in metadata
    assert "semi_transparency" in metadata
    assert metadata.get("embedded_width_px")
    assert item.asset.current_version.analysis.image_width > 0


def test_validation_attaches_to_existing_order_and_locks_sheet():
    user, customer, project = create_customer_scope(email="validate@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    order = Order.objects.create(customer=customer, created_by=user)
    project.converted_order = order
    project.save(update_fields=["converted_order", "updated_at"])
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Validée")
    service.add_occurrence(sheet=sheet, asset_version_public_id=version.public_id, actor=user)
    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)
    sheet.refresh_from_db()
    sheet.status = GangSheet.Status.RENDERING
    sheet.save(update_fields=["status", "updated_at"])
    sheet = GangSheetRenderService().render(sheet_public_id=sheet.public_id)

    validated = service.validate_sheet(sheet=sheet, actor=user)

    assert validated.status == GangSheet.Status.VALIDATED
    assert validated.order == order
    with pytest.raises(GangSheetDomainError, match="plus modifiable"):
        service.auto_place(sheet=validated, actor=user)
