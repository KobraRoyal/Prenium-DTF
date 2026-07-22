import hashlib
from decimal import Decimal

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import B2BOrderProjectService, ProjectDomainError
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
from apps.orders.models import Order
from apps.uploads.models import Asset, AssetAnalysis, AssetVersion, OrderUpload
from apps.uploads.services.asset_analysis import AssetAnalysisService
from apps.uploads.services.assets import AssetService
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


def test_occurrences_auto_place_without_overlap_and_height_is_automatic():
    user, customer, project = create_customer_scope(email="layout@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Compacte")
    first = service.add_occurrence(
        sheet=sheet, asset_version_public_id=version.public_id, actor=user
    )
    sheet.refresh_from_db()
    second = service.duplicate_occurrence(sheet=sheet, item_public_id=first.public_id, actor=user)

    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=user)
    sheet.refresh_from_db()
    items = list(sheet.items.all())

    assert {item.public_id for item in items} == {first.public_id, second.public_id}
    assert GangSheetGeometryService().issues(sheet=sheet, items=items) == []
    assert sheet.height_mm >= Decimal("60.00")
    assert sheet.surface_sqm > 0


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
        width_mm="270.00",
        height_mm="270.00",
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
        (Decimal("5.00"), Decimal("5.00")),
        (Decimal("108.00"), Decimal("5.00")),
        (Decimal("211.00"), Decimal("5.00")),
        (Decimal("5.00"), Decimal("58.00")),
        (Decimal("108.00"), Decimal("58.00")),
        (Decimal("211.00"), Decimal("58.00")),
    }
    assert GangSheetGeometryService().issues(sheet=sheet, items=items) == []


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
    raw_review = AssetService().technical_review_for_item(item=item)
    production_review = AssetService().production_review_for_item(item=item)

    assert raw_review["label"] == "Résolution insuffisante"
    assert production_review["label"] == "Contrôle du fichier HD"
    assert production_review["resolution_display"] == "PDF hybride"
    assert production_review["effective_dpi"] is None
    assert production_review["can_confirm"] is True
    assert "thin_zone" in item.asset.current_version.analysis.metadata
    assert "semi_transparency" in item.asset.current_version.analysis.metadata


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
