import json

import pytest
from apps.b2b_order_projects.models import B2BOrderProject
from django.test import override_settings
from django.urls import reverse

from .helpers import create_scope


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_member_can_delete_draft_project_via_api():
    member, customer, member_client = create_scope("member-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        created_by=member,
        project_number="GANG-SHEET-2026-999991",
        name="Projet à supprimer",
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    assert member_client.delete(detail_url).status_code == 204
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_submitted_project_without_conversion_can_be_deleted():
    _user, customer, client = create_scope("submitted-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="GANG-SHEET-2026-999990",
        name="Transmise",
        status=B2BOrderProject.Status.SUBMITTED,
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    assert client.delete(detail_url).status_code == 204
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_under_review_project_cannot_be_deleted():
    _user, customer, client = create_scope("review-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="GANG-SHEET-2026-999989",
        name="En contrôle",
        status=B2BOrderProject.Status.UNDER_REVIEW,
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    response = client.delete(detail_url)
    assert response.status_code == 400
    assert response.json()["code"] == "PROJECT_NOT_DELETABLE"
    assert B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_portal_delete_redirects_to_list_with_toast():
    _user, customer, client = create_scope("portal-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        project_number="GANG-SHEET-2026-999988",
        name="Portail",
    )
    delete_url = reverse(
        "portal:client-order-project-cancel",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    response = client.post(delete_url)
    assert response.status_code == 302
    assert response.url == reverse(
        "portal:client-order-project-list",
        kwargs={"customer_public_id": customer.public_id},
    )
    toast = json.loads(response.headers["X-Prenium-Toast"])
    assert toast["message"] == "Commande supprimée."
    assert toast["variant"] == "success"
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_delete_is_scoped_to_customer():
    owner_a, customer_a, _client_a = create_scope("owner-a@example.com")
    _owner_b, customer_b, client_b = create_scope("owner-b@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer_a,
        created_by=owner_a,
        project_number="GANG-SHEET-2026-999987",
        name="Scope A",
    )
    detail_url = reverse(
        "b2b_order_projects:client-detail",
        kwargs={"customer_public_id": customer_b.public_id, "project_public_id": project.public_id},
    )
    assert client_b.delete(detail_url).status_code == 404
    assert B2BOrderProject.objects.filter(pk=project.pk).exists()


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_delete_project_clears_legacy_placement_and_halftone_rows():
    import hashlib
    from io import BytesIO

    from apps.b2b_order_projects.models import B2BOrderProjectItem
    from apps.uploads.models import Asset, AssetVersion
    from django.core.files.uploadedfile import SimpleUploadedFile
    from django.db import connection
    from PIL import Image

    def table_exists(name: str) -> bool:
        return name in connection.introspection.table_names()

    if not table_exists("uploads_assetplacementanalysis"):
        pytest.skip("Table legacy uploads_assetplacementanalysis absente")

    user, customer, client = create_scope("legacy-fk-delete@example.com")
    project = B2BOrderProject.objects.create(
        customer=customer,
        created_by=user,
        project_number="CMD-2026-999980",
        name="Avec analyses legacy",
        status=B2BOrderProject.Status.DRAFT,
    )
    png = BytesIO()
    Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(png, format="PNG")
    content = png.getvalue()
    asset = Asset.objects.create(customer=customer, created_by=user, name="logo.png")
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=user,
        version_number=1,
        file=SimpleUploadedFile("logo.png", content, content_type="image/png"),
        original_filename="logo.png",
        mime_type="image/png",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    item = B2BOrderProjectItem.objects.create(
        customer=customer,
        project=project,
        asset=asset,
        name="Logo",
        width_mm="100.00",
        height_mm="50.00",
        quantity=1,
        sort_order=1,
    )

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO uploads_assetplacementanalysis (
                created_at, updated_at, public_id, customer_id, asset_version_id,
                b2b_item_id, width_mm, height_mm, crop_metadata, status,
                analysis_error, input_hash, generation, warnings, metadata,
                thin_zone_overlay, semi_transparency_overlay, fade_region_overlay
            ) VALUES (
                NOW(), NOW(), gen_random_uuid(), %s, %s,
                %s, 100.00, 50.00, '{}'::jsonb, 'pass',
                '', %s, 1, '[]'::jsonb, '{}'::jsonb,
                '', '', ''
            )
            """,
            [customer.id, version.id, item.id, "b" * 64],
        )
        if table_exists("uploads_assethalftonederivative"):
            cursor.execute(
                """
                INSERT INTO uploads_assethalftonederivative (
                    created_at, updated_at, public_id, status, input_hash,
                    generation, algorithm_version, preset, error_message, metadata,
                    preview, production_file, output_sha256, selected_for_production,
                    output_size_bytes, asset_version_id, b2b_item_id, customer_id
                ) VALUES (
                    NOW(), NOW(), gen_random_uuid(), 'ready', %s,
                    1, 'v1', 'default', '', '{}'::jsonb,
                    '', '', '', false,
                    0, %s, %s, %s
                )
                """,
                ["c" * 64, version.id, item.id, customer.id],
            )

    delete_url = reverse(
        "portal:client-order-project-cancel",
        kwargs={"customer_public_id": customer.public_id, "project_public_id": project.public_id},
    )
    response = client.post(delete_url)
    assert response.status_code == 302
    assert not B2BOrderProject.objects.filter(pk=project.pk).exists()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM uploads_assetplacementanalysis WHERE b2b_item_id = %s",
            [item.id],
        )
        assert cursor.fetchone()[0] == 0
