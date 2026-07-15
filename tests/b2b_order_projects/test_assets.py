from io import BytesIO
from unittest.mock import patch

import pymupdf
import pytest
from apps.auditlog.models import AuditLogEntry
from apps.b2b_order_projects.models import B2BOrderProject
from apps.b2b_order_projects.services import B2BOrderProjectService
from apps.customers.models import Customer, CustomerMembership
from apps.uploads.models import AssetAnalysis, AssetVersion
from apps.uploads.services.asset_analysis import AssetAnalysisService
from apps.uploads.services.assets import AssetDomainError, AssetService
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from psd_tools import PSDImage
from reportlab.pdfgen.canvas import Canvas
from rest_framework.test import APIClient

from .helpers import png_upload


def multi_format_upload(format_name):
    output = BytesIO()
    if format_name in {"pdf", "ai_pdf"}:
        document = Canvas(output, pagesize=(200, 100))
        document.setFillColorRGB(0.1, 0.4, 0.8)
        document.rect(10, 10, 180, 80, fill=1)
        document.showPage()
        document.save()
        name = "design.ai" if format_name == "ai_pdf" else "design.pdf"
        mime_type = "application/octet-stream" if format_name == "ai_pdf" else "application/pdf"
    elif format_name == "tiff":
        Image.new("RGBA", (160, 90), (255, 0, 0, 128)).save(output, format="TIFF", dpi=(300, 300))
        name, mime_type = "design.tiff", "application/octet-stream"
    elif format_name == "psd":
        PSDImage.new("RGB", (160, 90), color=(1.0, 0.2, 0.1)).save(output)
        name, mime_type = "design.psd", "application/octet-stream"
    elif format_name == "eps":
        output.write(
            b"%!PS-Adobe-3.0 EPSF-3.0\n"
            b"%%BoundingBox: 0 0 200 100\n"
            b"0.1 0.4 0.8 setrgbcolor\n"
            b"10 10 180 80 rectfill\nshowpage\n%%EOF\n"
        )
        name, mime_type = "design.eps", "application/octet-stream"
    else:
        raise AssertionError(f"Unknown preview fixture: {format_name}")
    return SimpleUploadedFile(name, output.getvalue(), content_type=mime_type)


def project_scope(email="asset@example.com"):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name="Asset client", b2b_order_projects_enabled=True)
    CustomerMembership.objects.create(customer=customer, user=user)
    project = B2BOrderProjectService().create_project(
        customer=customer, actor=user, data={"name": "Projet assets"}, source="test"
    )
    item = B2BOrderProjectService().add_item(
        project=project,
        actor=user,
        data={"name": "Logo", "width_mm": 100, "height_mm": 50, "quantity": 2},
        source="test",
    )
    return user, customer, project, item


@pytest.mark.django_db
def test_asset_versions_are_immutable_analyzed_and_audited():
    user, _customer, project, item = project_scope()
    service = AssetService()
    first = service.attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )
    analyzed = AssetAnalysisService().analyze(version_public_id=first.public_id, source="test")

    project.refresh_from_db()
    first.refresh_from_db()
    assert analyzed.analysis.image_width == 120
    assert first.sha256 and len(first.sha256) == 64
    assert project.status == B2BOrderProject.Status.ACTION_REQUIRED
    B2BOrderProjectService().confirm_item_analysis(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        data={"support_color_hex": "#112233"},
        source="test.confirmation",
    )
    project.refresh_from_db()
    assert project.status == B2BOrderProject.Status.READY_TO_SUBMIT
    AssetAnalysisService().analyze(version_public_id=first.public_id, source="test.retry")
    assert AssetAnalysis.objects.filter(version=first).count() == 1

    with pytest.raises(AssetDomainError) as replacement_closed:
        service.replace_project_item_file(
            project=project,
            item_public_id=item.public_id,
            actor=user,
            uploaded_file=png_upload("logo-v2.png", color=(0, 0, 255, 180)),
            source="test",
        )
    assert replacement_closed.value.code == "ASSET_REPLACEMENT_CLOSED"
    assert AssetVersion.objects.filter(asset=first.asset).count() == 1


@pytest.mark.django_db
def test_pending_asset_can_be_replaced_before_analysis_starts_and_is_audited():
    user, _customer, project, item = project_scope("replace-pending@example.com")
    service = AssetService()
    first = service.attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )

    assert first.analysis_status == AssetVersion.AnalysisStatus.PENDING
    item.refresh_from_db()
    assert service.can_replace_project_item_file(item=item) is True
    second = service.replace_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload("logo-v2.png", color=(0, 0, 255, 180)),
        source="test",
    )

    assert second.version_number == 2
    assert second.replaced_version == first
    assert AssetVersion.objects.filter(asset=first.asset).count() == 2
    assert AuditLogEntry.objects.filter(
        action="asset.version_replaced", target_public_id=first.asset.public_id
    ).exists()


@pytest.mark.django_db
def test_file_analysis_never_schedules_an_order_created_email():
    user, _customer, project, item = project_scope("analysis-email@example.com")
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )

    with patch("apps.notifications.tasks.send_order_created_email_task.delay") as task_delay:
        AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")

    task_delay.assert_not_called()


@pytest.mark.django_db
def test_requested_auto_size_is_applied_once_and_preserves_later_edits():
    user, _customer, project, item = project_scope("auto-size@example.com")
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
        auto_size_requested=True,
    )

    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    item.refresh_from_db()
    version.refresh_from_db()
    assert str(item.width_mm) == "10.16"
    assert str(item.height_mm) == "6.77"
    assert version.auto_size_requested is False

    item.width_mm = 42
    item.height_mm = 24
    item.save(update_fields=["width_mm", "height_mm", "updated_at"])
    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test.retry")
    item.refresh_from_db()
    assert str(item.width_mm) == "42.00"
    assert str(item.height_mm) == "24.00"


@pytest.mark.django_db
@override_settings(B2B_RECOMMENDED_DPI=300, B2B_MIN_ACCEPTABLE_DPI=200)
def test_technical_review_reports_resolution_levels():
    user, _customer, project, item = project_scope("quality-levels@example.com")
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )
    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    item.refresh_from_db()

    review = AssetService().technical_review_for_item(item=item)

    assert review["level"] == "error"
    assert review["label"] == "Résolution insuffisante"
    assert review["effective_dpi"] < 200
    assert review["can_confirm"] is True
    assert review["confirmed"] is False

    item.width_mm = "10.16"
    item.height_mm = "6.77"
    item.save(update_fields=["width_mm", "height_mm", "updated_at"])
    assert AssetService().technical_review_for_item(item=item)["level"] == "good"

    item.width_mm = "15.24"
    item.height_mm = "10.16"
    item.save(update_fields=["width_mm", "height_mm", "updated_at"])
    assert AssetService().technical_review_for_item(item=item)["level"] == "warning"


@pytest.mark.django_db
def test_pdf_auto_size_uses_page_dimensions_not_preview_dpi():
    user, _customer, project, item = project_scope("pdf-dpi@example.com")
    output = BytesIO()
    document = Canvas(output, pagesize=(200, 100))
    document.rect(10, 10, 180, 80, fill=1)
    document.showPage()
    document.save()

    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=SimpleUploadedFile(
            "design.pdf",
            output.getvalue(),
            content_type="application/pdf",
        ),
        source="test",
        auto_size_requested=True,
    )

    analyzed = AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    item.refresh_from_db()

    assert analyzed.analysis.dpi_x is None
    assert analyzed.analysis.dpi_y is None
    assert str(item.width_mm) == "70.56"
    assert str(item.height_mm) == "35.28"
    assert AssetService().effective_dpi_for_item(item=item) is None
    review = AssetService().technical_review_for_item(item=item)
    assert review["level"] == "good"
    assert review["resolution_display"] == "OK"
    assert review["is_vector"] is True


@pytest.mark.django_db
def test_pure_vector_pdf_edges_are_not_reported_as_semi_transparency():
    user, _customer, project, item = project_scope("pdf-vector-alpha@example.com")
    output = BytesIO()
    document = Canvas(output, pagesize=(200, 100))
    document.setFillColorRGB(0.1, 0.4, 0.8)
    document.circle(100, 50, 35, stroke=0, fill=1)
    document.showPage()
    document.save()

    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=SimpleUploadedFile(
            "vector-circle.pdf",
            output.getvalue(),
            content_type="application/pdf",
        ),
        source="test",
    )

    analyzed = AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    review = AssetService().technical_review_for_item(item=item)

    assert analyzed.analysis.metadata["is_pure_vector"] is True
    assert analyzed.analysis.metadata["semi_transparency"] == {
        "detected": False,
        "min_alpha": 33,
        "max_alpha": 250,
        "pixel_count": 0,
        "coverage_percent": 0.0,
        "skipped": True,
        "skip_reason": "pure_vector_source",
    }
    assert not analyzed.analysis.semi_transparency_overlay
    assert review["semi_transparency"]["detected"] is False
    assert all("semi-transparentes" not in issue for issue in review["issues"])


@pytest.mark.django_db
@override_settings(B2B_RECOMMENDED_DPI=300, B2B_MIN_ACCEPTABLE_DPI=200)
def test_pdf_auto_size_uses_embedded_display_size_for_mixed_documents():
    user, _customer, project, item = project_scope("pdf-mixed@example.com")
    image_buffer = BytesIO()
    Image.new("RGB", (600, 300), (255, 0, 0)).save(image_buffer, format="JPEG", dpi=(300, 300))
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 144, 72), stream=image_buffer.getvalue())
    pdf_bytes = document.tobytes()
    document.close()

    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=SimpleUploadedFile(
            "mixed-design.pdf",
            pdf_bytes,
            content_type="application/pdf",
        ),
        source="test",
        auto_size_requested=True,
    )

    analyzed = AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    item.refresh_from_db()

    assert analyzed.analysis.dpi_x == pytest.approx(300.0, rel=0.01)
    assert str(item.width_mm) == "50.80"
    assert str(item.height_mm) == "25.40"
    assert AssetService().effective_dpi_for_item(item=item) == 300.0
    review = AssetService().technical_review_for_item(item=item)
    assert review["level"] == "good"
    assert review["is_vector"] is False


@pytest.mark.django_db
@override_settings(B2B_RECOMMENDED_DPI=300, B2B_MIN_ACCEPTABLE_DPI=200)
def test_pdf_auto_size_uses_artboard_for_illustrator_mixed_documents():
    user, _customer, project, item = project_scope("pdf-artboard@example.com")
    image_buffer = BytesIO()
    Image.new("RGB", (986, 657), (255, 0, 0)).save(image_buffer, format="JPEG", quality=95)
    document = pymupdf.open()
    page = document.new_page(width=1021.67, height=1355.35)
    page.insert_image(
        pymupdf.Rect(393.545166015625, 1142.0823974609375, 630.0609130859375, 1299.759521484375),
        stream=image_buffer.getvalue(),
    )
    shape = page.new_shape()
    shape.draw_rect(
        pymupdf.Rect(
            369.1451110839844,
            1222.22216796875,
            385.80712890625,
            1231.7591552734375,
        )
    )
    shape.finish(color=(0, 0, 0), fill=(0, 0, 0))
    shape.commit()
    pdf_bytes = document.tobytes()
    document.close()

    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=SimpleUploadedFile(
            "chemise-artboard.pdf",
            pdf_bytes,
            content_type="application/pdf",
        ),
        source="test",
        auto_size_requested=True,
    )

    analyzed = AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    item.refresh_from_db()

    assert analyzed.analysis.metadata["uses_artboard_dimensions"] is True
    assert analyzed.analysis.metadata["has_vector_artwork"] is True
    assert str(item.width_mm) == "360.42"
    assert str(item.height_mm) == "478.14"
    assert analyzed.analysis.dpi_x == pytest.approx(300.0, rel=0.02)
    assert analyzed.analysis.metadata["is_pure_vector"] is False
    assert analyzed.analysis.metadata["semi_transparency"]["skipped"] is False
    review = AssetService().technical_review_for_item(item=item)
    assert review["level"] == "good"
    assert review["resolution_display"] == "300 DPI"
    assert review["effective_dpi"] == pytest.approx(300.0, rel=0.02)


@pytest.mark.django_db
@override_settings(B2B_RECOMMENDED_DPI=300, B2B_MIN_ACCEPTABLE_DPI=200)
def test_png_effective_dpi_matches_source_metadata_at_intrinsic_size():
    user, _customer, project, item = project_scope("png-dpi@example.com")
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
        auto_size_requested=True,
    )
    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    item.refresh_from_db()

    assert AssetService().effective_dpi_for_item(item=item) == 300.0
    assert AssetService().technical_review_for_item(item=item)["level"] == "good"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("format_name", "expected_format"),
    [
        ("pdf", "PDF"),
        ("ai_pdf", "AI compatible PDF"),
        ("tiff", "TIFF"),
        ("psd", "PSD"),
        ("eps", "EPS"),
    ],
)
def test_asset_analysis_generates_protected_preview_for_professional_formats(
    format_name, expected_format
):
    user, _customer, project, item = project_scope(f"preview-{format_name}@example.com")
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=multi_format_upload(format_name),
        source="test",
        auto_size_requested=True,
    )

    AssetAnalysisService().analyze(version_public_id=version.public_id, source="test")
    version.refresh_from_db()
    item.refresh_from_db()

    assert version.analysis_status in {
        AssetVersion.AnalysisStatus.READY,
        AssetVersion.AnalysisStatus.WARNING,
    }
    assert version.analysis.thumbnail
    assert version.analysis.image_width > 0
    assert version.analysis.image_height > 0
    assert version.analysis.metadata["format"] == expected_format
    if format_name in {"pdf", "ai_pdf", "eps"}:
        assert version.analysis.metadata["is_pure_vector"] is True
        assert version.analysis.metadata["semi_transparency"]["skipped"] is True
    assert item.width_mm > 0
    assert item.height_mm > 0

    preview = AssetService().prepare_project_preview(
        project=project,
        item_public_id=item.public_id,
    )
    assert preview is not None
    assert preview[1] == "image/webp"


@pytest.mark.django_db
def test_invalid_asset_does_not_attach_to_item():
    user, _customer, project, item = project_scope("invalid@example.com")
    with pytest.raises(AssetDomainError) as error:
        AssetService().attach_project_item_file(
            project=project,
            item_public_id=item.public_id,
            actor=user,
            uploaded_file=SimpleUploadedFile("fake.png", b"not an image", content_type="image/png"),
            source="test",
        )
    assert error.value.code == "INVALID_ASSET_FILE"
    item.refresh_from_db()
    assert item.asset is None


@pytest.mark.django_db
@override_settings(B2B_DTF_ORDER_PROJECT_ENABLED=True)
def test_asset_api_download_is_mediated_and_cross_tenant_is_hidden():
    user, customer, project, item = project_scope("download@example.com")
    version = AssetService().attach_project_item_file(
        project=project,
        item_public_id=item.public_id,
        actor=user,
        uploaded_file=png_upload(),
        source="test",
    )
    client = APIClient()
    client.login(email=user.email, password="pass")
    download_url = reverse(
        "b2b_order_projects:client-item-asset-download",
        kwargs={
            "customer_public_id": customer.public_id,
            "project_public_id": project.public_id,
            "item_public_id": item.public_id,
        },
    )
    version.file.open("rb")
    expected_content = version.file.read()
    version.file.close()
    response = client.get(download_url)
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert b"".join(response.streaming_content) == expected_content

    other = Customer.objects.create(name="Autre", b2b_order_projects_enabled=True)
    CustomerMembership.objects.create(customer=other, user=user)
    hidden_url = reverse(
        "b2b_order_projects:client-item-asset-download",
        kwargs={
            "customer_public_id": other.public_id,
            "project_public_id": project.public_id,
            "item_public_id": item.public_id,
        },
    )
    assert client.get(hidden_url).status_code == 404
