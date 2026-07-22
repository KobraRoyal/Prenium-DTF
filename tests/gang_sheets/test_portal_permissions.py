import json
from decimal import Decimal
from io import BytesIO

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.customers.models import CustomerMembership
from apps.gang_sheets.models import GangSheet, GangSheetSourceAsset
from apps.gang_sheets.services import GangSheetRenderService, GangSheetService
from apps.orders.models import Order
from apps.uploads.models import AssetAnalysis, AssetVersion
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image, ImageDraw

from .helpers import attach_png_asset, create_customer_scope, mark_gang_sheet_drive_synced

pytestmark = pytest.mark.django_db


def test_gang_sheet_library_uses_the_shared_portal_design_system(client):
    user, customer, _project = create_customer_scope(email="studio-library@example.com")
    client.force_login(user)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Mes Gang Sheets" in content
    assert 'class="gang-library-head"' in content
    assert 'class="gang-sheet-toolbar"' not in content
    assert 'id="create-gang-sheet-dialog"' in content
    assert 'data-dialog-open="create-gang-sheet-dialog"' in content
    assert "Nouvelle planche" in content
    assert "Créer et ouvrir le studio" in content
    assert 'class="gang-workflow"' not in content
    assert "Créer une planche autonome" not in content


def test_gang_sheet_library_exposes_filters_and_a_scoped_inline_preview(client):
    user, customer, _project = create_customer_scope(email="studio-preview@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Collection été")
    sheet.preview_file = SimpleUploadedFile(
        "preview.png",
        b"preview",
        content_type="image/png",
    )
    sheet.save(update_fields=["preview_file", "updated_at"])
    client.force_login(user)
    preview_url = reverse(
        "portal:client-gang-sheet-preview-download",
        kwargs={
            "customer_public_id": customer.public_id,
            "sheet_public_id": sheet.public_id,
        },
    )

    library = client.get(
        reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": customer.public_id},
        )
    )

    assert library.status_code == 200
    content = library.content.decode()
    assert 'class="gang-sheet-toolbar"' in content
    assert "Brouillons" in content
    assert "En traitement" in content
    assert "Validées" in content
    assert "Commandées" in content
    assert 'data-status-group="draft"' in content
    assert f"{preview_url}?display=inline" in content
    assert "Reprendre la composition" in content
    assert "Supprimer la planche" not in content
    assert 'aria-label="Actions pour la planche Collection été"' in content

    inline_preview = client.get(f"{preview_url}?display=inline")
    assert inline_preview.status_code == 200
    assert inline_preview["Cache-Control"] == "private, no-store"
    assert inline_preview["Content-Disposition"].startswith("inline;")


def test_gang_sheet_inline_preview_remains_customer_scoped(client):
    owner, customer, _project = create_customer_scope(email="preview-owner@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=owner, name="Privée")
    sheet.preview_file = SimpleUploadedFile(
        "private-preview.png",
        b"preview",
        content_type="image/png",
    )
    sheet.save(update_fields=["preview_file", "updated_at"])
    outsider, outsider_customer, _outsider_project = create_customer_scope(
        email="preview-outsider@example.com"
    )
    client.force_login(outsider)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-preview-download",
            kwargs={
                "customer_public_id": outsider_customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {"display": "inline"},
    )

    assert response.status_code == 404


def test_gang_sheet_editor_exposes_the_professional_four_step_workflow(client):
    user, customer, _project = create_customer_scope(email="studio-editor@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Studio moderne")
    client.force_login(user)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
        )
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert 'aria-label="Progression de la planche"' in content
    assert 'aria-current="step"' in content
    assert "Vos visuels" in content
    assert "Plan de travail" in content
    assert "Contrôle de production" in content
    assert "Rendu de production sécurisé" in content
    assert 'data-mobile-panel-tab="canvas"' in content
    assert "data-zoom-reset" in content
    assert "data-status-detail" in content
    assert "Espacement auto-imposition" in content
    assert "data-spacing-x" in content
    assert "data-spacing-y" in content
    assert "data-apply-spacing" in content
    assert "Alignement" in content
    assert 'value="selection" data-align-reference' in content
    assert 'value="sheet" data-align-reference' in content
    assert 'data-align="left"' in content
    assert 'data-align="center-x"' in content
    assert 'data-align="right"' in content
    assert 'data-align="top"' in content
    assert 'data-align="center-y"' in content
    assert 'data-align="bottom"' in content
    assert "data-undo-layout" in content
    assert "data-redo-layout" in content
    assert "data-snap-toggle" in content
    assert "data-select-all" in content
    assert "data-touch-multiselect" in content
    assert 'data-distribute="horizontal"' in content
    assert 'data-distribute="vertical"' in content
    assert "data-selection-gap" in content
    assert 'data-apply-selection-gap="horizontal"' in content
    assert 'data-apply-selection-gap="vertical"' in content
    assert "data-batch-delete-url" in content
    assert "data-delete-selected" in content
    assert "data-canvas-clear-zone" in content
    assert "Répétition" not in content
    assert "Créer la grille" not in content
    assert 'id="gang-asset-dialog"' in content
    assert 'data-file-picker-dialog="gang-asset-dialog"' in content
    assert 'name="files" multiple' in content
    assert "Vérifier l’import" in content
    assert "Recadrage non destructif" in content
    assert 'name="crop_manifest"' in content
    assert "data-gang-crop-box" in content
    assert "data-crop-manual" in content
    assert "data-crop-auto" in content
    assert "Illustration + pixels" in content
    assert "gang-editor__delete" in content
    assert "Supprimer cette Gang Sheet ?" in content


def test_owner_can_delete_a_standalone_draft_from_the_portal(client):
    user, customer, _project = create_customer_scope(email="delete-owner@example.com")
    sheet = GangSheetService().create_sheet(
        customer=customer,
        actor=user,
        name="Brouillon supprimable",
    )
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {"return_to": "editor"},
    )

    assert response.status_code == 302
    assert response.url == reverse(
        "portal:client-gang-sheet-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )
    toast = json.loads(response.headers["X-Prenium-Toast"])
    assert toast == {"message": "Gang Sheet supprimée.", "variant": "success"}
    assert not GangSheet.objects.filter(pk=sheet.pk).exists()


def test_readonly_member_cannot_delete_a_gang_sheet(client):
    user, customer, project = create_customer_scope(
        email="readonly-delete@example.com",
        role=CustomerMembership.Role.READONLY,
    )
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Lecture seule")
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert response.status_code == 403
    assert GangSheet.objects.filter(pk=sheet.pk).exists()
    assert project.customer == customer


def test_delete_is_scoped_to_the_current_customer(client):
    owner_a, customer_a, _project_a = create_customer_scope(email="delete-a@example.com")
    _owner_b, customer_b, _project_b = create_customer_scope(email="delete-b@example.com")
    sheet = GangSheetService().create_sheet(
        customer=customer_a,
        actor=owner_a,
        name="Privée A",
    )
    client.force_login(_owner_b)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer_b.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert response.status_code == 404
    assert GangSheet.objects.filter(pk=sheet.pk).exists()


def test_validated_sheet_delete_is_refused_and_returns_to_the_editor(client):
    user, customer, _project = create_customer_scope(email="delete-validated@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Validée")
    sheet.status = GangSheet.Status.VALIDATED
    sheet.save(update_fields=["status", "updated_at"])
    client.force_login(user)
    editor_url = reverse(
        "portal:client-gang-sheet-editor",
        kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
    )

    response = client.post(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {"return_to": "editor"},
    )

    assert response.status_code == 302
    assert response.url == editor_url
    toast = json.loads(response.headers["X-Prenium-Toast"])
    assert toast["variant"] == "error"
    assert "traçabilité" in toast["message"]
    assert GangSheet.objects.filter(pk=sheet.pk).exists()


def test_gang_sheet_delete_endpoint_rejects_get(client):
    user, customer, _project = create_customer_scope(email="delete-get@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="POST uniquement")
    client.force_login(user)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert response.status_code == 405
    assert GangSheet.objects.filter(pk=sheet.pk).exists()


def test_owner_can_delete_a_gang_sheet_after_it_was_converted_to_an_order(
    client,
    monkeypatch,
):
    user, customer, _project = create_customer_scope(email="delete-ordered-portal@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Déjà commandée")
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
    project = service.create_order_project(sheet=sheet, actor=user, source="test")
    production_asset = project.items.get().asset
    order = Order.objects.create(customer=customer, created_by=user)
    project.status = B2BOrderProject.Status.CONVERTED
    project.converted_order = order
    project.save(update_fields=["status", "converted_order", "updated_at"])
    sheet.refresh_from_db()
    sheet.order = order
    sheet.save(update_fields=["order", "updated_at"])
    sheet = mark_gang_sheet_drive_synced(sheet)
    client.force_login(user)
    library_url = reverse(
        "portal:client-gang-sheet-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )

    library_response = client.get(library_url)
    delete_response = client.post(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert library_response.status_code == 200
    library_content = library_response.content.decode()
    assert "Retirer cette Gang Sheet ?" in library_content
    assert "Le projet de commande et son fichier HD seront conservés" in library_content
    assert "La commande déjà créée restera également intacte" in library_content
    assert delete_response.status_code == 302
    assert delete_response.url == library_url
    assert not GangSheet.objects.filter(pk=sheet.pk).exists()
    assert B2BOrderProject.objects.filter(pk=project.pk, converted_order=order).exists()
    assert Order.objects.filter(pk=order.pk).exists()
    assert production_asset.versions.exists()


def test_delete_button_is_available_as_soon_as_hd_is_secured_in_order_project(
    client,
    monkeypatch,
):
    user, customer, _project = create_customer_scope(email="delete-ready-project-ui@example.com")
    service = GangSheetService()
    sheet = service.create_sheet(customer=customer, actor=user, name="Prête sans commande")
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
    project = service.create_order_project(sheet=sheet, actor=user, source="test")
    production_asset = project.items.get().asset
    sheet.refresh_from_db()
    sheet = mark_gang_sheet_drive_synced(sheet)
    client.force_login(user)
    library_url = reverse(
        "portal:client-gang-sheet-list-create",
        kwargs={"customer_public_id": customer.public_id},
    )

    library_response = client.get(library_url)
    delete_response = client.post(
        reverse(
            "portal:client-gang-sheet-delete",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert library_response.status_code == 200
    content = library_response.content.decode()
    assert "Retirer cette Gang Sheet ?" in content
    assert "Le projet de commande et son fichier HD seront conservés" in content
    assert "commande déjà créée" not in content
    assert delete_response.status_code == 302
    assert not GangSheet.objects.filter(pk=sheet.pk).exists()
    assert B2BOrderProject.objects.filter(pk=project.pk).exists()
    assert production_asset.versions.exists()


def test_client_cannot_read_another_customer_sheet(client):
    user, customer, _project = create_customer_scope(email="reader@example.com")
    other_user, other_customer, other_project = create_customer_scope(email="hidden@example.com")
    sheet = GangSheetService().create_sheet(project=other_project, actor=other_user, name="Secret")
    client.force_login(user)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": other_customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert response.status_code == 403
    assert customer != other_customer


def test_readonly_member_cannot_mutate_layout(client):
    user, customer, project = create_customer_scope(
        email="readonly@example.com", role=CustomerMembership.Role.READONLY
    )
    sheet = GangSheetService().create_sheet(project=project, actor=user, name="Lecture")
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-item-add",
            kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
        ),
        {"asset_version_public_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 403


def test_owner_can_delete_multiple_selected_occurrences_in_one_request(client):
    user, customer, project = create_customer_scope(email="batch-delete-owner@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Suppression portail")
    items = service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=3,
        actor=user,
    )
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-items-delete-batch",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        data=json.dumps({"item_public_ids": [str(items[0].public_id), str(items[1].public_id)]}),
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2
    assert list(sheet.items.values_list("public_id", flat=True)) == [items[2].public_id]


def test_batch_delete_rejects_invalid_json_selection_before_mutation(client):
    user, customer, project = create_customer_scope(email="batch-delete-invalid@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Entrées invalides")
    item = service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    sheet.refresh_from_db()
    initial_revision = sheet.revision
    url = reverse(
        "portal:client-gang-sheet-items-delete-batch",
        kwargs={
            "customer_public_id": customer.public_id,
            "sheet_public_id": sheet.public_id,
        },
    )
    invalid_requests = (
        (b"\xff", "INVALID_JSON"),
        ("[]", "INVALID_JSON"),
        ("null", "INVALID_JSON"),
        ('"selection"', "INVALID_JSON"),
        (json.dumps({"item_public_ids": []}), "ITEM_SELECTION_REQUIRED"),
        (json.dumps({"item_public_ids": "invalid"}), "INVALID_ITEM_SELECTION"),
        (json.dumps({"item_public_ids": ["not-a-uuid"]}), "INVALID_ITEM_SELECTION"),
        (
            json.dumps({"item_public_ids": [str(item.public_id)] * 1001}),
            "BATCH_DELETE_LIMIT_EXCEEDED",
        ),
    )
    client.force_login(user)

    for body, expected_code in invalid_requests:
        response = client.post(url, data=body, content_type="application/json")

        assert response.status_code == 400
        assert response.json()["error"]["code"] == expected_code
        sheet.refresh_from_db()
        assert sheet.revision == initial_revision
        assert sheet.items.filter(public_id=item.public_id).exists()

    assert not AuditLogEntry.objects.filter(
        action="gang_sheet.items_batch_deleted",
        target_public_id=sheet.public_id,
    ).exists()


def test_batch_delete_is_readonly_protected_and_tenant_scoped(client):
    owner, customer, project = create_customer_scope(email="batch-delete-scope@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=owner)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=owner, name="Planche privée")
    item = service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=owner,
    )
    outsider, outsider_customer, _outsider_project = create_customer_scope(
        email="batch-delete-outsider@example.com"
    )
    readonly, readonly_customer, readonly_project = create_customer_scope(
        email="batch-delete-readonly@example.com",
        role=CustomerMembership.Role.READONLY,
    )
    _readonly_asset, readonly_version = attach_png_asset(
        customer=readonly_customer,
        project=readonly_project,
        user=readonly,
    )
    readonly_sheet = service.create_sheet(
        project=readonly_project,
        actor=readonly,
        name="Lecture seule",
    )
    readonly_item = service.add_occurrence(
        sheet=readonly_sheet,
        asset_version_public_id=readonly_version.public_id,
        actor=readonly,
    )

    client.force_login(outsider)
    cross_tenant_response = client.post(
        reverse(
            "portal:client-gang-sheet-items-delete-batch",
            kwargs={
                "customer_public_id": outsider_customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        data=json.dumps({"item_public_ids": [str(item.public_id)]}),
        content_type="application/json",
    )
    client.force_login(readonly)
    readonly_response = client.post(
        reverse(
            "portal:client-gang-sheet-items-delete-batch",
            kwargs={
                "customer_public_id": readonly_customer.public_id,
                "sheet_public_id": readonly_sheet.public_id,
            },
        ),
        data=json.dumps({"item_public_ids": [str(readonly_item.public_id)]}),
        content_type="application/json",
    )

    assert cross_tenant_response.status_code == 404
    assert readonly_response.status_code == 403
    assert sheet.items.filter(public_id=item.public_id).exists()
    assert readonly_sheet.items.filter(public_id=readonly_item.public_id).exists()


def test_owner_can_apply_axis_spacing_through_the_scoped_workflow_action(client):
    user, customer, project = create_customer_scope(email="spacing-owner@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Espacement portail")
    service.add_occurrences(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        quantity=2,
        actor=user,
    )
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-workflow-action",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
                "action": "auto-place",
            },
        ),
        {"spacing_x_mm": "6.50", "spacing_y_mm": "9.25"},
    )

    sheet.refresh_from_db()
    assert response.status_code == 200
    assert response.json()["message"] == "Espacement appliqué et planche réorganisée."
    assert sheet.item_spacing_x_mm == Decimal("6.50")
    assert sheet.item_spacing_y_mm == Decimal("9.25")


def test_axis_spacing_action_is_readonly_protected_and_tenant_scoped(client):
    owner_a, customer_a, project_a = create_customer_scope(email="spacing-a@example.com")
    _asset_a, version_a = attach_png_asset(
        customer=customer_a,
        project=project_a,
        user=owner_a,
    )
    service = GangSheetService()
    sheet_a = service.create_sheet(project=project_a, actor=owner_a, name="Privée A")
    service.add_occurrence(
        sheet=sheet_a,
        asset_version_public_id=version_a.public_id,
        actor=owner_a,
    )
    owner_b, customer_b, _project_b = create_customer_scope(email="spacing-b@example.com")
    readonly, customer_c, project_c = create_customer_scope(
        email="spacing-readonly@example.com",
        role=CustomerMembership.Role.READONLY,
    )
    sheet_c = service.create_sheet(project=project_c, actor=readonly, name="Lecture seule")

    client.force_login(owner_b)
    cross_tenant_response = client.post(
        reverse(
            "portal:client-gang-sheet-workflow-action",
            kwargs={
                "customer_public_id": customer_b.public_id,
                "sheet_public_id": sheet_a.public_id,
                "action": "auto-place",
            },
        ),
        {"spacing_x_mm": "6", "spacing_y_mm": "8"},
    )
    client.force_login(readonly)
    readonly_response = client.post(
        reverse(
            "portal:client-gang-sheet-workflow-action",
            kwargs={
                "customer_public_id": customer_c.public_id,
                "sheet_public_id": sheet_c.public_id,
                "action": "auto-place",
            },
        ),
        {"spacing_x_mm": "6", "spacing_y_mm": "8"},
    )

    sheet_a.refresh_from_db()
    assert cross_tenant_response.status_code == 404
    assert readonly_response.status_code == 403
    assert sheet_a.item_spacing_x_mm == sheet_a.item_spacing_mm
    assert sheet_a.item_spacing_y_mm == sheet_a.item_spacing_mm


def test_owner_can_add_a_quantity_and_auto_place_from_the_gallery(client):
    user, customer, project = create_customer_scope(email="gallery-owner@example.com")
    _asset, version = attach_png_asset(
        customer=customer, project=project, user=user, width_mm="70.00", height_mm="35.00"
    )
    sheet = GangSheetService().create_sheet(project=project, actor=user, name="Galerie")
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-item-add",
            kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
        ),
        {
            "asset_version_public_id": version.public_id,
            "quantity": "4",
            "auto_place": "1",
        },
    )

    assert response.status_code == 201
    assert response.json()["created_count"] == 4
    assert sheet.items.count() == 4


def test_owner_can_create_sheet_and_upload_gallery_without_project(client, monkeypatch):
    user, customer, _project = create_customer_scope(email="autonomous-owner@example.com")
    client.force_login(user)
    create_response = client.post(
        reverse(
            "portal:client-gang-sheet-list-create",
            kwargs={"customer_public_id": customer.public_id},
        ),
        {"name": "Série autonome"},
    )
    sheet = GangSheet.objects.get(name="Série autonome")
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )

    upload_response = client.post(
        reverse(
            "portal:client-gang-sheet-asset-upload",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "files": SimpleUploadedFile(
                "logo.png",
                b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                content_type="image/png",
            )
        },
    )

    assert create_response.status_code == 302
    assert sheet.project is None
    assert upload_response.status_code == 302
    assert sheet.source_assets.count() == 1


def test_owner_can_upload_multiple_visuals_with_independent_non_destructive_crops(
    client,
    monkeypatch,
):
    user, customer, _project = create_customer_scope(email="crop-upload@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Crops privés")
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-asset-upload",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "files": [
                SimpleUploadedFile(
                    "left.png",
                    b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                    content_type="image/png",
                ),
                SimpleUploadedFile(
                    "right.png",
                    b"\x89PNG\r\n\x1a\n" + b"1" * 64,
                    content_type="image/png",
                ),
            ],
            "crop_manifest": json.dumps(
                [
                    {"index": 0, "x": 0.1, "y": 0.2, "width": 0.5, "height": 0.6},
                    {"index": 1, "x": 0.2, "y": 0.1, "width": 0.7, "height": 0.8},
                ]
            ),
        },
    )

    assert response.status_code == 302
    sources = list(sheet.source_assets.order_by("sort_order"))
    assert len(sources) == 2
    assert sources[0].crop_x == Decimal("0.100000")
    assert sources[0].crop_width == Decimal("0.500000")
    assert sources[1].crop_y == Decimal("0.100000")
    assert sources[1].crop_height == Decimal("0.800000")


def test_auto_crop_upload_recomputes_visible_pixels_server_side(client, monkeypatch):
    user, customer, _project = create_customer_scope(email="auto-crop-upload@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="Crop auto")
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )
    image = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 10, 79, 69), fill=(20, 90, 220, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    image.close()
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-asset-upload",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "files": SimpleUploadedFile(
                "auto.png",
                output.getvalue(),
                content_type="image/png",
            ),
            "crop_manifest": json.dumps(
                [
                    {
                        "index": 0,
                        "mode": "auto",
                        "x": 0,
                        "y": 0,
                        "width": 1,
                        "height": 1,
                    }
                ]
            ),
        },
    )

    assert response.status_code == 302
    source = sheet.source_assets.get()
    assert source.crop_x == Decimal("0.180000")
    assert source.crop_y == Decimal("0.100000")
    assert source.crop_width == Decimal("0.640000")
    assert source.crop_height == Decimal("0.800000")
    event = AuditLogEntry.objects.get(action="gang_sheet.source_uploaded")
    assert event.metadata["crop_mode"] == "auto"
    assert event.metadata["auto_crop"]["content_kind"] == "raster"
    assert event.metadata["auto_crop"]["basis"] == "visible_pixels"


def test_invalid_or_cross_tenant_crop_upload_is_rejected(client, monkeypatch):
    owner, customer, _project = create_customer_scope(email="crop-owner@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=owner, name="Crop protégé")
    outsider, outsider_customer, _outsider_project = create_customer_scope(
        email="crop-outsider@example.com"
    )
    monkeypatch.setattr(
        "apps.uploads.services.assets.AssetService.schedule_analysis",
        lambda self, version: None,
    )
    client.force_login(owner)
    invalid_response = client.post(
        reverse(
            "portal:client-gang-sheet-asset-upload",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "files": SimpleUploadedFile(
                "invalid.png",
                b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                content_type="image/png",
            ),
            "crop_manifest": '[{"index":0,"x":0.8,"y":0,"width":0.4,"height":1}]',
        },
    )
    client.force_login(outsider)
    cross_tenant_response = client.post(
        reverse(
            "portal:client-gang-sheet-asset-upload",
            kwargs={
                "customer_public_id": outsider_customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        ),
        {
            "files": SimpleUploadedFile(
                "private.png",
                b"\x89PNG\r\n\x1a\n" + b"0" * 64,
                content_type="image/png",
            ),
            "crop_manifest": '[{"index":0,"mode":"auto","x":0,"y":0,"width":1,"height":1}]',
        },
    )

    assert invalid_response.status_code == 302
    assert json.loads(invalid_response.headers["X-Prenium-Toast"])["variant"] == "error"
    assert cross_tenant_response.status_code == 404
    assert sheet.source_assets.count() == 0


def test_pending_gallery_refreshes_itself_and_exposes_visual_when_analysis_is_ready(client):
    user, customer, project = create_customer_scope(email="dynamic-gallery@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=user)
    sheet = GangSheetService().create_sheet(project=project, actor=user, name="Galerie dynamique")
    version.analysis_status = version.AnalysisStatus.PENDING
    version.save(update_fields=["analysis_status", "updated_at"])
    client.force_login(user)
    gallery_url = reverse(
        "portal:client-gang-sheet-asset-gallery",
        kwargs={"customer_public_id": customer.public_id, "sheet_public_id": sheet.public_id},
    )

    pending_response = client.get(gallery_url)

    assert pending_response.status_code == 200
    assert pending_response["Cache-Control"] == "private, no-store"
    pending_content = pending_response.content.decode()
    assert 'data-has-pending="true"' in pending_content
    assert f'hx-get="{gallery_url}"' in pending_content
    assert 'hx-trigger="every 2s"' in pending_content
    assert 'data-asset-ready="false"' in pending_content

    version.analysis_status = version.AnalysisStatus.READY
    version.save(update_fields=["analysis_status", "updated_at"])
    ready_response = client.get(gallery_url)

    assert ready_response.status_code == 200
    ready_content = ready_response.content.decode()
    assert 'data-has-pending="false"' in ready_content
    assert 'hx-trigger="every 2s"' not in ready_content
    assert 'data-asset-ready="true"' in ready_content
    assert "Placer sur la planche" in ready_content


def test_owner_can_remove_an_unused_visual_from_gallery_with_htmx(client):
    user, customer, project = create_customer_scope(email="remove-gallery-portal@example.com")
    asset, _version = attach_png_asset(customer=customer, project=project, user=user)
    sheet = GangSheetService().create_sheet(project=project, actor=user, name="Galerie à nettoyer")
    source_asset = sheet.source_assets.get(asset=asset)
    client.force_login(user)

    response = client.post(
        reverse(
            "portal:client-gang-sheet-source-asset-remove",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
                "source_asset_public_id": source_asset.public_id,
            },
        ),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    assert not GangSheetSourceAsset.objects.filter(pk=source_asset.pk).exists()
    assert asset.versions.exists()
    assert "Galerie vide" in response.content.decode()
    assert json.loads(response.headers["X-Prenium-Toast"]) == {
        "message": "Visuel retiré de la galerie.",
        "variant": "success",
    }


def test_used_visual_must_be_removed_from_composition_before_gallery(client):
    user, customer, project = create_customer_scope(email="used-gallery-portal@example.com")
    asset, version = attach_png_asset(customer=customer, project=project, user=user)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=user, name="Galerie utilisée")
    source_asset = sheet.source_assets.get(asset=asset)
    service.add_occurrence(
        sheet=sheet,
        asset_version_public_id=version.public_id,
        actor=user,
    )
    client.force_login(user)

    editor_response = client.get(
        reverse(
            "portal:client-gang-sheet-editor",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )
    remove_response = client.post(
        reverse(
            "portal:client-gang-sheet-source-asset-remove",
            kwargs={
                "customer_public_id": customer.public_id,
                "sheet_public_id": sheet.public_id,
                "source_asset_public_id": source_asset.public_id,
            },
        ),
        HTTP_HX_REQUEST="true",
    )

    editor_content = editor_response.content.decode()
    assert editor_response.status_code == 200
    assert ">Utilisé</button>" in editor_content
    assert "Supprimez d’abord toutes les occurrences" in editor_content
    assert remove_response.status_code == 400
    assert GangSheetSourceAsset.objects.filter(pk=source_asset.pk).exists()
    toast = json.loads(remove_response.headers["X-Prenium-Toast"])
    assert toast["variant"] == "error"
    assert "encore utilisé" in toast["message"]


def test_gallery_visual_removal_is_readonly_protected_and_tenant_scoped(client):
    owner_a, customer_a, project_a = create_customer_scope(email="remove-gallery-a@example.com")
    asset_a, _version_a = attach_png_asset(
        customer=customer_a,
        project=project_a,
        user=owner_a,
    )
    sheet_a = GangSheetService().create_sheet(
        project=project_a,
        actor=owner_a,
        name="Galerie privée A",
    )
    source_asset_a = sheet_a.source_assets.get(asset=asset_a)
    owner_b, customer_b, _project_b = create_customer_scope(
        email="remove-gallery-owner-b@example.com",
    )
    readonly_c, customer_c, _project_c = create_customer_scope(
        email="remove-gallery-readonly-c@example.com",
        role=CustomerMembership.Role.READONLY,
    )
    own_sheet_c = GangSheetService().create_sheet(
        customer=customer_c,
        actor=readonly_c,
        name="Lecture seule C",
    )
    client.force_login(owner_b)

    cross_tenant_response = client.post(
        reverse(
            "portal:client-gang-sheet-source-asset-remove",
            kwargs={
                "customer_public_id": customer_b.public_id,
                "sheet_public_id": sheet_a.public_id,
                "source_asset_public_id": source_asset_a.public_id,
            },
        )
    )
    client.force_login(readonly_c)
    readonly_response = client.post(
        reverse(
            "portal:client-gang-sheet-source-asset-remove",
            kwargs={
                "customer_public_id": customer_c.public_id,
                "sheet_public_id": own_sheet_c.public_id,
                "source_asset_public_id": source_asset_a.public_id,
            },
        )
    )

    assert cross_tenant_response.status_code == 404
    assert readonly_response.status_code == 403
    assert GangSheetSourceAsset.objects.filter(pk=source_asset_a.pk).exists()


def test_asset_gallery_refresh_is_scoped_to_the_current_customer(client):
    owner_a, customer_a, project_a = create_customer_scope(email="gallery-a@example.com")
    _asset, _version = attach_png_asset(
        customer=customer_a,
        project=project_a,
        user=owner_a,
    )
    sheet = GangSheetService().create_sheet(project=project_a, actor=owner_a, name="Galerie A")
    owner_b, customer_b, _project_b = create_customer_scope(email="gallery-b@example.com")
    client.force_login(owner_b)

    response = client.get(
        reverse(
            "portal:client-gang-sheet-asset-gallery",
            kwargs={
                "customer_public_id": customer_b.public_id,
                "sheet_public_id": sheet.public_id,
            },
        )
    )

    assert response.status_code == 404


def test_client_cannot_download_generated_production_asset_from_order_project(client, monkeypatch):
    owner, customer, _project = create_customer_scope(email="private-project-output@example.com")
    sheet = GangSheetService().create_sheet(customer=customer, actor=owner, name="Sortie privée")
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
    project = GangSheetService().create_order_project(sheet=sheet, actor=owner)
    item = project.items.get()
    version = item.asset.current_version
    version.analysis_status = AssetVersion.AnalysisStatus.WARNING
    version.save(update_fields=["analysis_status", "updated_at"])
    AssetAnalysis.objects.create(
        customer=customer,
        version=version,
        image_width=638,
        image_height=2126,
        dpi_x="29.00",
        dpi_y="29.00",
        warnings=["Diagnostic historique erroné"],
        metadata={
            "thin_zone": {"detected": True, "coverage_percent": 2.0},
            "semi_transparency": {"detected": True, "coverage_percent": 3.0},
        },
    )
    client.force_login(owner)

    detail_response = client.get(
        reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )

    confirmation_url = reverse(
        "portal:client-order-project-item-action",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project.public_id,
            "item_public_id": item.public_id,
            "action": "confirm-analysis",
        },
    )
    invalid_confirmation_response = client.post(
        confirmation_url,
        {
            "confirm_analysis": "on",
            "support_color_hex": "#multicolor",
        },
    )
    confirmation_response = client.post(
        confirmation_url,
        {
            "confirm_analysis": "on",
            "support_color_hex": "#112233",
        },
    )
    item.refresh_from_db()
    version.analysis_status = AssetVersion.AnalysisStatus.PENDING
    version.save(update_fields=["analysis_status", "updated_at"])
    pending_detail_response = client.get(
        reverse(
            "portal:client-order-project-detail",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
            },
        )
    )

    response = client.get(
        reverse(
            "portal:client-order-project-item-asset-download",
            kwargs={
                "customer_public_id": customer.public_id,
                "project_public_id": project.public_id,
                "item_public_id": item.public_id,
            },
        )
    )

    detail_content = detail_response.content.decode()
    assert detail_response.status_code == 200
    assert "Contrôle du fichier HD" in detail_content
    assert "PDF HD hybride" in detail_content
    assert "Résolution insuffisante" not in detail_content
    assert "Diagnostic historique erroné" in detail_content
    assert "Zones sous 0,5 mm affichées" in detail_content
    assert "Semi-transparences affichées" in detail_content
    assert "Couleur du support obligatoire" in detail_content
    assert "Indiquez la couleur unie exacte du textile" in detail_content
    assert "Valider pour commander" in detail_content
    assert invalid_confirmation_response.status_code == 400
    assert (
        "Indiquez la couleur unie exacte du support"
        in invalid_confirmation_response.content.decode()
    )
    assert confirmation_response.status_code == 200
    assert item.support_color_hex == "#112233"
    assert item.client_confirmed_asset_version == version
    pending_detail_content = pending_detail_response.content.decode()
    assert pending_detail_response.status_code == 200
    assert "data-analysis-pending" in pending_detail_content
    assert 'hx-trigger="load delay:1400ms"' in pending_detail_content
    assert "Contrôle du fichier HD" not in pending_detail_content
    assert response.status_code == 404


def test_final_file_requires_staff_portal_and_production_permission(client):
    owner, customer, project = create_customer_scope(email="owner-final@example.com")
    _asset, version = attach_png_asset(customer=customer, project=project, user=owner)
    service = GangSheetService()
    sheet = service.create_sheet(project=project, actor=owner, name="HD privée")
    service.add_occurrence(sheet=sheet, asset_version_public_id=version.public_id, actor=owner)
    sheet.refresh_from_db()
    service.auto_place(sheet=sheet, actor=owner)
    sheet.refresh_from_db()
    sheet.status = GangSheet.Status.RENDERING
    sheet.save(update_fields=["status", "updated_at"])
    sheet = GangSheetRenderService().render(sheet_public_id=sheet.public_id)
    sheet.status = GangSheet.Status.VALIDATED
    sheet.save(update_fields=["status", "updated_at"])
    staff = get_user_model().objects.create_user(
        email="staff-final@example.com", password="pass", is_staff=True
    )
    staff.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client.force_login(staff)
    url = reverse(
        "portal:staff-gang-sheet-final-download", kwargs={"sheet_public_id": sheet.public_id}
    )

    assert client.get(url).status_code == 403

    staff.user_permissions.add(Permission.objects.get(codename="download_final_gangsheet"))
    response = client.get(url)
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    assert response["Content-Disposition"].startswith("attachment;")
