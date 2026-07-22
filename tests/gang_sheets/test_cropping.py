from io import BytesIO

import pymupdf
import pytest
from apps.gang_sheets.services.cropping import (
    CROP_MODE_AUTO,
    AutoCropService,
    CropValidationError,
    parse_crop_manifest,
)
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw


def _image_upload(*, image: Image.Image, name: str, image_format: str, mime_type: str):
    output = BytesIO()
    image.save(output, format=image_format, quality=95)
    return SimpleUploadedFile(name, output.getvalue(), content_type=mime_type)


def _pdf_upload(*, mixed: bool = False):
    document = pymupdf.open()
    page = document.new_page(width=200, height=100)
    page.draw_rect(pymupdf.Rect(120 if mixed else 50, 20, 180 if mixed else 150, 80))
    if mixed:
        raster = Image.new("RGBA", (31, 23), (220, 40, 80, 255))
        output = BytesIO()
        raster.save(output, format="PNG")
        raster.close()
        page.insert_image(pymupdf.Rect(10, 10, 40, 40), stream=output.getvalue())
    content = document.tobytes()
    document.close()
    return SimpleUploadedFile("illustration.pdf", content, content_type="application/pdf")


def test_auto_crop_uses_visible_alpha_pixels_for_transparent_raster():
    image = Image.new("RGBA", (100, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 10, 79, 69), fill=(40, 90, 230, 255))
    upload = _image_upload(
        image=image,
        name="transparent.png",
        image_format="PNG",
        mime_type="image/png",
    )
    image.close()

    result = AutoCropService().detect(upload)

    assert result.content_kind == "raster"
    assert result.basis == "visible_pixels"
    assert result.crop.to_metadata() == {
        "x": "0.180000",
        "y": "0.100000",
        "width": "0.640000",
        "height": "0.800000",
    }


def test_auto_crop_detects_illustration_against_opaque_raster_background():
    image = Image.new("RGB", (120, 90), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 20, 89, 69), fill=(20, 80, 210))
    upload = _image_upload(
        image=image,
        name="illustration.jpg",
        image_format="JPEG",
        mime_type="image/jpeg",
    )
    image.close()

    result = AutoCropService().detect(upload)

    assert result.content_kind == "raster"
    assert 0.20 <= float(result.crop.x) <= 0.25
    assert 0.50 <= float(result.crop.width) <= 0.56
    assert 0.18 <= float(result.crop.y) <= 0.23
    assert 0.61 <= float(result.crop.height) <= 0.63


def test_auto_crop_uses_native_pdf_objects_for_vector_document():
    result = AutoCropService().detect(_pdf_upload())

    assert result.content_kind == "vector"
    assert result.basis == "native_pdf_objects"
    assert 0.24 <= float(result.crop.x) <= 0.26
    assert 0.49 <= float(result.crop.width) <= 0.52
    assert 0.19 <= float(result.crop.y) <= 0.21
    assert 0.59 <= float(result.crop.height) <= 0.62


def test_auto_crop_unites_vector_illustration_and_embedded_pixels_for_mixed_pdf():
    result = AutoCropService().detect(_pdf_upload(mixed=True))

    assert result.content_kind == "mixed"
    assert result.basis == "native_pdf_objects"
    assert 0.04 <= float(result.crop.x) <= 0.06
    assert 0.84 <= float(result.crop.width) <= 0.87
    assert 0.13 <= float(result.crop.y) <= 0.14
    assert 0.66 <= float(result.crop.height) <= 0.68


def test_crop_manifest_accepts_auto_mode_and_rejects_unknown_mode():
    parsed = parse_crop_manifest(
        '[{"index": 0, "mode": "auto", "x": 0, "y": 0, "width": 1, "height": 1}]',
        file_count=1,
    )

    assert parsed[0].mode == CROP_MODE_AUTO

    with pytest.raises(CropValidationError, match="mode de recadrage"):
        parse_crop_manifest(
            '[{"index": 0, "mode": "magic", "x": 0, "y": 0, "width": 1, "height": 1}]',
            file_count=1,
        )
