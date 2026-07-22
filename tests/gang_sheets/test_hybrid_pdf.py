from __future__ import annotations

import hashlib
from io import BytesIO

import pymupdf
import pytest
from apps.gang_sheets.models import GangSheet, GangSheetItem, GangSheetSourceAsset
from apps.gang_sheets.services import GangSheetRenderService, GangSheetService
from apps.gang_sheets.services.hybrid_pdf import MM_TO_POINTS, GangSheetHybridPdfComposer
from apps.uploads.models import Asset, AssetVersion
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from .helpers import create_customer_scope

pytestmark = pytest.mark.django_db


def _vector_pdf(*, with_link=False) -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(8, 8, 192, 92), color=(0.1, 0.6, 0.2), width=2)
    page.insert_text((24, 57), "VECTOR", fontsize=24, color=(0.1, 0.2, 0.6))
    if with_link:
        page.insert_link(
            {
                "kind": pymupdf.LINK_URI,
                "from": pymupdf.Rect(20, 30, 150, 70),
                "uri": "https://example.com/source-link",
            }
        )
    content = document.tobytes()
    document.close()
    return content


def _mixed_pdf() -> bytes:
    image_output = BytesIO()
    Image.new("RGB", (41, 23), (230, 50, 30)).save(image_output, format="PNG")
    document = pymupdf.open()
    page = document.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(5, 5, 195, 95), color=(0.1, 0.5, 0.2), width=2)
    page.insert_image(pymupdf.Rect(30, 20, 112, 66), stream=image_output.getvalue())
    content = document.tobytes()
    document.close()
    return content


def _transparent_png() -> bytes:
    output = BytesIO()
    image = Image.new("RGBA", (307, 149), (20, 120, 220, 145))
    image.save(output, format="PNG", dpi=(300, 300))
    image.close()
    return output.getvalue()


def _eps_vector() -> bytes:
    return b"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 200 100
1 0 0 setrgbcolor
5 setlinewidth
10 10 moveto 190 10 lineto 190 90 lineto 10 90 lineto closepath stroke
0 0.3 0.8 setrgbcolor
20 50 moveto 180 50 lineto stroke
showpage
%%EOF
"""


def _composition(
    *,
    email: str,
    content: bytes,
    filename: str,
    mime_type: str,
    width_mm="40.00",
    height_mm="20.00",
    rotation=0,
    crop=None,
):
    user, customer, _project = create_customer_scope(email=email)
    asset = Asset.objects.create(customer=customer, created_by=user, name=filename)
    version = AssetVersion.objects.create(
        customer=customer,
        asset=asset,
        uploaded_by=user,
        version_number=1,
        file=SimpleUploadedFile(filename, content, content_type=mime_type),
        original_filename=filename,
        mime_type=mime_type,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        analysis_status=AssetVersion.AnalysisStatus.READY,
    )
    asset.current_version = version
    asset.save(update_fields=["current_version", "updated_at"])
    sheet = GangSheetService().create_sheet(customer=customer, actor=user, name="PDF hybride")
    crop = crop or {}
    GangSheetSourceAsset.objects.create(
        customer=customer,
        sheet=sheet,
        asset=asset,
        added_by=user,
        width_mm=width_mm,
        height_mm=height_mm,
        crop_x=crop.get("x", "0"),
        crop_y=crop.get("y", "0"),
        crop_width=crop.get("width", "1"),
        crop_height=crop.get("height", "1"),
    )
    item = GangSheetItem.objects.create(
        customer=customer,
        sheet=sheet,
        asset_version=version,
        x_mm="5.00",
        y_mm="5.00",
        width_mm=width_mm,
        height_mm=height_mm,
        rotation=rotation,
        z_index=1,
    )
    return sheet, item


def test_render_service_preserves_vector_pdf_and_drops_source_annotations():
    sheet, item = _composition(
        email="hybrid-vector@example.com",
        content=_vector_pdf(with_link=True),
        filename="logo.pdf",
        mime_type="application/pdf",
    )
    sheet.status = GangSheet.Status.RENDERING
    sheet.save(update_fields=["status", "updated_at"])

    rendered = GangSheetRenderService().render(sheet_public_id=sheet.public_id)

    assert rendered.status == GangSheet.Status.READY
    rendered.final_file.open("rb")
    try:
        content = rendered.final_file.read()
    finally:
        rendered.final_file.close()
    with pymupdf.open(stream=content, filetype="pdf") as document:
        page = document[0]
        assert page.rect.width == pytest.approx(float(sheet.width_mm) * MM_TO_POINTS)
        assert page.rect.height == pytest.approx(float(sheet.height_mm) * MM_TO_POINTS)
        assert page.get_drawings()
        assert "VECTOR" in page.get_text()
        assert page.get_fonts(full=True)
        assert page.get_images(full=True) == []
        assert page.get_links() == []
        assert page.rect.contains(
            pymupdf.Rect(
                float(item.x_mm) * MM_TO_POINTS,
                float(item.y_mm) * MM_TO_POINTS,
                (float(item.x_mm) + float(item.width_mm)) * MM_TO_POINTS,
                (float(item.y_mm) + float(item.height_mm)) * MM_TO_POINTS,
            )
        )


def test_mixed_pdf_keeps_vector_commands_and_native_raster_pixels():
    sheet, item = _composition(
        email="hybrid-mixed@example.com",
        content=_mixed_pdf(),
        filename="mixed.pdf",
        mime_type="application/pdf",
        crop={"x": "0.20", "y": "0.10", "width": "0.70", "height": "0.80"},
    )

    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        page = document[0]
        assert page.get_drawings()
        images = page.get_images(full=True)
        assert any(image[2:4] == (41, 23) for image in images)


def test_cropped_vector_pdf_keeps_vector_commands_without_rasterizing():
    sheet, item = _composition(
        email="hybrid-cropped-vector@example.com",
        content=_vector_pdf(),
        filename="cropped-logo.pdf",
        mime_type="application/pdf",
        crop={"x": "0.25", "y": "0.10", "width": "0.50", "height": "0.80"},
    )

    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        page = document[0]
        assert page.get_drawings()
        assert page.get_images(full=True) == []
        assert page.get_fonts(full=True)


def test_transparent_png_is_embedded_at_source_definition_with_alpha_mask():
    sheet, item = _composition(
        email="hybrid-raster@example.com",
        content=_transparent_png(),
        filename="transparent.png",
        mime_type="image/png",
    )

    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        images = document[0].get_images(full=True)
        assert any(image[2:4] == (307, 149) and image[1] > 0 for image in images)
        assert document[0].get_drawings() == []


def test_cropped_raster_keeps_only_native_pixels_without_resampling():
    sheet, item = _composition(
        email="hybrid-cropped-raster@example.com",
        content=_transparent_png(),
        filename="cropped-transparent.png",
        mime_type="image/png",
        crop={"x": "0.25", "y": "0.20", "width": "0.50", "height": "0.50"},
    )

    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        images = document[0].get_images(full=True)
        assert any(image[2:4] == (155, 76) and image[1] > 0 for image in images)


def test_rotated_raster_uses_the_exact_effective_print_dimensions():
    sheet, item = _composition(
        email="hybrid-rotation@example.com",
        content=_transparent_png(),
        filename="rotate.png",
        mime_type="image/png",
        width_mm="40.00",
        height_mm="20.00",
        rotation=90,
    )

    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        image = document[0].get_images(full=True)[0]
        image_rect = document[0].get_image_rects(image[0])[0]
        assert image_rect.width == pytest.approx(20 * MM_TO_POINTS, abs=0.02)
        assert image_rect.height == pytest.approx(40 * MM_TO_POINTS, abs=0.02)


def test_eps_is_converted_to_pdf_without_rasterizing_vector_commands():
    sheet, item = _composition(
        email="hybrid-eps@example.com",
        content=_eps_vector(),
        filename="logo.eps",
        mime_type="application/postscript",
    )

    content = GangSheetHybridPdfComposer().compose(sheet=sheet, items=[item])

    with pymupdf.open(stream=content, filetype="pdf") as document:
        page = document[0]
        assert page.get_drawings()
        assert page.get_images(full=True) == []
