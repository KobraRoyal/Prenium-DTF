from io import BytesIO

import pymupdf
from apps.uploads.services.asset_semi_transparency import AssetSemiTransparencyAnalyzer
from PIL import Image, ImageDraw
from reportlab.lib.colors import Color
from reportlab.pdfgen.canvas import Canvas


def test_detects_partial_alpha_values_used_in_anti_alias():
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 10, 100, 70), fill=(10, 10, 10, 255))
    draw.ellipse((18, 8, 102, 72), outline=(10, 10, 10, 120), width=2)

    result = AssetSemiTransparencyAnalyzer().analyze(image=image)
    image.close()

    assert result.detected is True
    assert result.metadata["pixel_count"] >= 48
    assert result.overlay is not None
    with Image.open(BytesIO(result.overlay)) as overlay:
        assert overlay.size[0] <= 480
        assert overlay.getchannel("A").getbbox() is not None


def test_ignores_fully_opaque_or_fully_transparent_pixels():
    opaque = Image.new("RGBA", (80, 60), (255, 0, 0, 255))
    transparent = Image.new("RGBA", (80, 60), (255, 0, 0, 0))

    opaque_result = AssetSemiTransparencyAnalyzer().analyze(image=opaque)
    transparent_result = AssetSemiTransparencyAnalyzer().analyze(image=transparent)
    opaque.close()
    transparent.close()

    assert opaque_result.detected is False
    assert opaque_result.overlay is None
    assert transparent_result.detected is False
    assert transparent_result.overlay is None


def test_requires_minimum_pixel_count_before_flagging():
    image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    image.putpixel((10, 10), (0, 0, 0, 128))

    result = AssetSemiTransparencyAnalyzer().analyze(image=image)
    image.close()

    assert result.detected is False
    assert result.metadata["pixel_count"] == 1
    assert result.overlay is None


def test_requires_relative_coverage_on_large_images():
    image = Image.new("RGBA", (2000, 2000), (255, 0, 0, 255))
    for index in range(48):
        image.putpixel((index * 3, index * 3), (255, 0, 0, 128))

    result = AssetSemiTransparencyAnalyzer().analyze(image=image)
    image.close()

    assert result.metadata["pixel_count"] == 48
    assert result.metadata["coverage_percent"] < 0.02
    assert result.detected is False


def test_detects_soft_shadow_at_min_alpha_boundary():
    image = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for index in range(50):
        image.putpixel((index, 5), (0, 0, 0, 16))

    result = AssetSemiTransparencyAnalyzer().analyze(image=image)
    image.close()

    assert result.metadata["pixel_count"] == 50
    assert result.detected is True


def test_ignores_rasterization_alpha_when_source_is_pure_vector():
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((18, 8, 102, 72), fill=(10, 10, 10, 255))
    draw.ellipse((17, 7, 103, 73), outline=(10, 10, 10, 120), width=2)

    result = AssetSemiTransparencyAnalyzer().analyze(
        image=image,
        source_is_pure_vector=True,
    )
    image.close()

    assert result.detected is False
    assert result.overlay is None
    assert result.metadata["pixel_count"] == 0
    assert result.metadata["skipped"] is True
    assert result.metadata["skip_reason"] == "pure_vector_source"


def test_analyzes_pure_vector_when_source_declares_opacity():
    image = Image.new("RGBA", (120, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 10, 100, 70), fill=(10, 10, 10, 128))

    result = AssetSemiTransparencyAnalyzer().analyze(
        image=image,
        source_is_pure_vector=True,
        source_has_opacity=True,
        erode_render_antialias=True,
    )
    image.close()

    assert result.detected is True
    assert result.metadata["skipped"] is False


def test_eroded_render_ignores_thin_mu_pdf_style_rings_but_keeps_fills():
    thin = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(thin)
    draw.ellipse((40, 20, 160, 100), fill=(10, 10, 10, 255))
    # 1 px fringe — typical MuPDF AA after rasterization
    for alpha in (80, 160):
        draw.ellipse((39, 19, 161, 101), outline=(10, 10, 10, alpha), width=1)

    thin_result = AssetSemiTransparencyAnalyzer().analyze(
        image=thin,
        erode_render_antialias=True,
    )
    thin.close()
    assert thin_result.detected is False

    fill = Image.new("RGBA", (200, 120), (0, 0, 0, 0))
    ImageDraw.Draw(fill).ellipse((40, 20, 160, 100), fill=(10, 10, 10, 128))
    fill_result = AssetSemiTransparencyAnalyzer().analyze(
        image=fill,
        erode_render_antialias=True,
    )
    fill.close()
    assert fill_result.detected is True


def test_rgb_without_alpha_is_not_detected_but_flagged():
    image = Image.new("RGB", (120, 80), (255, 255, 255))
    ImageDraw.Draw(image).ellipse((20, 10, 100, 70), fill=(10, 10, 10))

    result = AssetSemiTransparencyAnalyzer().analyze(image=image)
    image.close()

    assert result.detected is False
    assert result.metadata["alpha_channel_present"] is False


def test_pdf_mixed_opaque_jpeg_plus_vector_is_not_flagged():
    image_buffer = BytesIO()
    Image.new("RGB", (600, 300), (255, 0, 0)).save(image_buffer, format="JPEG")
    document = pymupdf.open()
    page = document.new_page(width=400, height=200)
    page.insert_image(pymupdf.Rect(40, 40, 360, 160), stream=image_buffer.getvalue())
    shape = page.new_shape()
    shape.draw_circle(pymupdf.Point(50, 50), 30)
    shape.finish(fill=(0, 0, 0))
    shape.commit()
    pdf_bytes = document.tobytes()
    document.close()

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as rendered_doc:
        rendered_page = rendered_doc.load_page(0)
        pixmap = rendered_page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2),
            colorspace=pymupdf.csRGB,
            alpha=True,
        )
        preview = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)

    result = AssetSemiTransparencyAnalyzer().analyze_pdf_document(
        content=pdf_bytes,
        preview_image=preview,
        page_width_points=400,
        page_height_points=200,
        is_pure_vector=False,
        has_source_opacity=False,
    )
    preview.close()

    assert result.detected is False
    assert result.metadata["skipped"] is False


def test_pdf_embedded_soft_png_is_detected():
    png_buffer = BytesIO()
    png = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    for y in range(20, 80):
        for x in range(20, 180):
            png.putpixel((x, y), (255, 0, 0, 180))
    png.save(png_buffer, format="PNG")
    png.close()

    document = pymupdf.open()
    page = document.new_page(width=400, height=200)
    page.insert_image(pymupdf.Rect(50, 25, 350, 175), stream=png_buffer.getvalue())
    shape = page.new_shape()
    shape.draw_circle(pymupdf.Point(30, 30), 15)
    shape.finish(fill=(0, 0, 0))
    shape.commit()
    pdf_bytes = document.tobytes()
    document.close()

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as rendered_doc:
        rendered_page = rendered_doc.load_page(0)
        pixmap = rendered_page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2),
            colorspace=pymupdf.csRGB,
            alpha=True,
        )
        preview = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)

    result = AssetSemiTransparencyAnalyzer().analyze_pdf_document(
        content=pdf_bytes,
        preview_image=preview,
        page_width_points=400,
        page_height_points=200,
        is_pure_vector=False,
        has_source_opacity=False,
    )
    preview.close()

    assert result.detected is True
    assert result.overlay is not None


def test_pdf_vector_opacity_fill_is_detected():
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=(200, 100))
    canvas.setFillColor(Color(0.1, 0.4, 0.8, alpha=0.5))
    canvas.circle(100, 50, 35, stroke=0, fill=1)
    canvas.showPage()
    canvas.save()
    pdf_bytes = buffer.getvalue()

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        from apps.uploads.services.asset_dpi import pdf_document_has_source_opacity

        assert pdf_document_has_source_opacity(document, is_pure_vector=True) is True
        page = document.load_page(0)
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(2, 2),
            colorspace=pymupdf.csRGB,
            alpha=True,
        )
        preview = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)

    result = AssetSemiTransparencyAnalyzer().analyze_pdf_document(
        content=pdf_bytes,
        preview_image=preview,
        page_width_points=200,
        page_height_points=100,
        is_pure_vector=True,
        has_source_opacity=True,
    )
    preview.close()

    assert result.detected is True
    assert result.metadata["skipped"] is False
