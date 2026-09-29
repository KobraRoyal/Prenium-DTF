from io import BytesIO

import pymupdf
import pytest
from apps.customers.models import Customer
from apps.uploads.models import Asset, AssetVersion
from apps.uploads.services.asset_analysis import AssetAnalysisService
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image


def _pdf(*, pages: int = 1) -> bytes:
    document = pymupdf.open()
    for _ in range(pages):
        page = document.new_page(width=144, height=144)
        page.draw_rect(pymupdf.Rect(24, 24, 120, 120), fill=(0, 0, 0))
    content = document.tobytes()
    document.close()
    return content


def _tiff(*, frames: int = 1) -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    if frames == 1:
        image.save(output, format="TIFF", dpi=(300, 300))
    else:
        image.save(
            output, format="TIFF", dpi=(300, 300), save_all=True, append_images=[image.copy()]
        )
    return output.getvalue()


def _postscript() -> bytes:
    return (
        b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 144 144\n%%Pages: 1\n"
        b"newpath 24 24 moveto 120 24 lineto 120 120 lineto closepath fill\n"
        b"showpage\n%%EOF\n"
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("name", "mime_type", "content"),
    [
        ("artwork.pdf", "application/pdf", _pdf()),
        ("artwork.ai", "application/pdf", _pdf()),
        ("artwork.ai", "application/postscript", _postscript()),
        ("artwork.eps", "application/postscript", _postscript()),
        ("artwork.tiff", "image/tiff", _tiff()),
    ],
    ids=["pdf", "ai-pdf", "ai-postscript", "eps", "tiff"],
)
def test_clean_single_page_dtf_sources_can_reach_ready(
    settings, tmp_path, name, mime_type, content
):
    settings.MEDIA_ROOT = tmp_path
    customer = Customer.objects.create(name=f"Analyse {name}")
    asset = Asset.objects.create(customer=customer, name=name)
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        version_number=1,
        file=SimpleUploadedFile(name, content, content_type=mime_type),
        original_filename=name,
        mime_type=mime_type,
        size_bytes=len(content),
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])

    analyzed = AssetAnalysisService().analyze(
        version_public_id=version.public_id, source="test.dtf"
    )

    assert analyzed.analysis_status == AssetVersion.AnalysisStatus.READY, analyzed.analysis.warnings
    if mime_type == "application/pdf":
        assert analyzed.analysis.metadata["pages"] == 1
        assert analyzed.analysis.metadata["notices"]


@pytest.mark.django_db
def test_multipage_pdf_remains_warning_and_not_ready(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    customer = Customer.objects.create(name="Analyse multi-page")
    asset = Asset.objects.create(customer=customer, name="multi.pdf")
    content = _pdf(pages=2)
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        version_number=1,
        file=SimpleUploadedFile("multi.pdf", content, content_type="application/pdf"),
        original_filename="multi.pdf",
        mime_type="application/pdf",
        size_bytes=len(content),
    )

    analyzed = AssetAnalysisService().analyze(
        version_public_id=version.public_id, source="test.dtf"
    )

    assert analyzed.analysis_status == AssetVersion.AnalysisStatus.WARNING
    assert any("multipage" in warning for warning in analyzed.analysis.warnings)
