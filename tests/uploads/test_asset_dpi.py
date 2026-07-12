from io import BytesIO
from unittest.mock import Mock

import pymupdf
import pytest
from apps.uploads.services.asset_dpi import (
    extract_pdf_artboard_size_mm,
    extract_pdf_source_metrics,
    extract_pillow_dpi,
)
from apps.uploads.services.asset_preview import AssetPreviewRenderer
from PIL import Image
from reportlab.pdfgen.canvas import Canvas


def make_version(name, mime, content):
    version = Mock()
    version.original_filename = name
    version.mime_type = mime

    class FileWrapper:
        def open(self, mode="rb"):
            return None

        def close(self):
            return None

        def read(self):
            return content

    version.file = FileWrapper()
    return version


def test_extract_pillow_dpi_reads_png_metadata():
    buffer = BytesIO()
    Image.new("RGBA", (1200, 800), (255, 0, 0, 255)).save(buffer, format="PNG", dpi=(300, 300))
    buffer.seek(0)
    with Image.open(buffer) as image:
        assert extract_pillow_dpi(image) == (300.0, 300.0)


def test_extract_pdf_source_metrics_uses_embedded_image_resolution():
    image_buffer = BytesIO()
    Image.new("RGB", (600, 300), (255, 0, 0)).save(image_buffer, format="JPEG", dpi=(300, 300))
    document = pymupdf.open()
    page = document.new_page(width=200, height=100)
    page.insert_image(page.rect, stream=image_buffer.getvalue())
    metrics = extract_pdf_source_metrics(document, page)
    document.close()

    assert metrics.dpi_x == pytest.approx(300.0, rel=0.01)
    assert metrics.dpi_source == "embedded"
    assert metrics.width_px == 600
    assert metrics.height_px == 300
    assert metrics.page_width_in == pytest.approx(200 / 72, rel=0.01)
    assert metrics.display_width_in == pytest.approx(2.0, rel=0.01)
    assert metrics.display_height_in == pytest.approx(1.0, rel=0.01)
    assert metrics.placement_effective_dpi == pytest.approx(216.0, rel=0.01)


def test_extract_pdf_source_metrics_prefers_embedded_dpi_when_upscaled_on_page():
    image_buffer = BytesIO()
    Image.new("RGB", (1200, 1200), (255, 0, 0)).save(image_buffer, format="JPEG", dpi=(300, 300))
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=image_buffer.getvalue())
    metrics = extract_pdf_source_metrics(document, page)
    document.close()

    assert metrics.dpi_x == pytest.approx(300.0, rel=0.01)
    assert metrics.dpi_source == "embedded"
    assert metrics.display_width_in == pytest.approx(4.0, rel=0.01)
    assert metrics.display_height_in == pytest.approx(4.0, rel=0.01)
    assert metrics.placement_effective_dpi == pytest.approx(102.61, rel=0.01)


def test_extract_pdf_source_metrics_tracks_partial_embedded_display_size():
    image_buffer = BytesIO()
    Image.new("RGB", (600, 300), (255, 0, 0)).save(image_buffer, format="JPEG", dpi=(300, 300))
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_image(pymupdf.Rect(0, 0, 144, 72), stream=image_buffer.getvalue())
    metrics = extract_pdf_source_metrics(document, page)
    document.close()

    assert metrics.display_width_in == pytest.approx(2.0, rel=0.01)
    assert metrics.display_height_in == pytest.approx(1.0, rel=0.01)
    assert metrics.dpi_x == pytest.approx(300.0, rel=0.01)
    assert metrics.dpi_source == "embedded"
    assert metrics.page_width_in == pytest.approx(595 / 72, rel=0.01)
    assert metrics.uses_artboard_dimensions is False


def test_extract_pdf_source_metrics_uses_artboard_for_vector_mixed_documents():
    image_buffer = BytesIO()
    Image.new("RGB", (986, 657), (255, 0, 0)).save(image_buffer, format="JPEG", quality=95)
    document = pymupdf.open()
    page = document.new_page(width=1021.67, height=1355.35)
    page.insert_image(
        pymupdf.Rect(393.545166015625, 1142.0823974609375, 630.0609130859375, 1299.759521484375),
        stream=image_buffer.getvalue(),
    )
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(369.1451110839844, 1222.22216796875, 385.80712890625, 1231.7591552734375))
    shape.finish(color=(0, 0, 0), fill=(0, 0, 0))
    shape.commit()
    metrics = extract_pdf_source_metrics(document, page)
    artboard = extract_pdf_artboard_size_mm(document, page)
    document.close()

    assert artboard == (pytest.approx(360.42, rel=0.01), pytest.approx(478.14, rel=0.01))
    assert metrics.uses_artboard_dimensions is True
    assert metrics.artboard_width_mm == pytest.approx(360.42, rel=0.01)
    assert metrics.artboard_height_mm == pytest.approx(478.14, rel=0.01)
    assert metrics.dpi_x == pytest.approx(300.0, rel=0.02)
    assert metrics.dimension_basis == "page"


def test_pdf_preview_does_not_report_render_dpi_as_source_dpi():
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(200, 100))
    canvas.rect(10, 10, 180, 80, fill=1)
    canvas.showPage()
    canvas.save()

    rendered = AssetPreviewRenderer().render(
        version=make_version("design.pdf", "application/pdf", buffer.getvalue())
    )

    assert rendered.dpi_x is None
    assert rendered.dpi_y is None
    assert rendered.metadata["render_dpi"] == 144.0
    assert rendered.metadata["dimension_basis"] == "page"
