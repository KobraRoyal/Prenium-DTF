from io import BytesIO

from apps.uploads.services.asset_thin_zones import AssetThinZoneAnalyzer
from PIL import Image, ImageDraw


def test_detects_only_details_thinner_than_half_a_millimeter_at_300_dpi():
    image = Image.new("RGBA", (300, 180), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 280, 31), fill=(0, 0, 0, 255))
    draw.rectangle((20, 80, 280, 83), fill=(0, 0, 0, 255))

    result = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=300,
        dpi_y=300,
        metadata={},
        probable_white_background=False,
    )
    image.close()

    assert result.detected is True
    assert result.metadata["threshold_pixels"] == 5.91
    assert result.metadata["scale_basis"] == "embedded_dpi"
    assert result.metadata["mask_basis"] == "transparency"
    assert result.overlay is not None
    with Image.open(BytesIO(result.overlay)) as overlay:
        assert overlay.size == (300, 180)
        assert overlay.getchannel("A").getbbox() == (19, 79, 282, 85)


def test_does_not_flag_a_thick_printed_shape():
    image = Image.new("RGBA", (180, 120), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((20, 30, 160, 60), fill=(0, 0, 0, 255))

    result = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=300,
        dpi_y=300,
        metadata={},
        probable_white_background=False,
    )
    image.close()

    assert result.detected is False
    assert result.overlay is None
    assert result.metadata["coverage_percent"] == 0.0


def test_uses_page_dimensions_for_vector_preview_scale():
    image = Image.new("RGBA", (720, 360), (0, 0, 0, 0))
    ImageDraw.Draw(image).line((40, 80, 680, 80), fill=(0, 0, 0, 255), width=1)

    result = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=None,
        dpi_y=None,
        metadata={"page_width_in": 10, "page_height_in": 5, "render_dpi": 144},
        probable_white_background=False,
    )
    image.close()

    assert result.detected is True
    assert result.metadata["scale_basis"] == "page_dimensions"
    assert result.metadata["threshold_pixels"] == 1.42


def test_prefers_item_placement_dimensions_over_embedded_dpi():
    image = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
    # 3 px bar: thin at 300 DPI (~0.25 mm) but thick enough at 50 mm placement (~0.75 mm)
    ImageDraw.Draw(image).rectangle((10, 40, 190, 42), fill=(0, 0, 0, 255))

    native = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=300,
        dpi_y=300,
        metadata={},
        probable_white_background=False,
    )
    placed = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=300,
        dpi_y=300,
        metadata={"placement_width_mm": 50, "placement_height_mm": 20},
        probable_white_background=False,
    )
    image.close()

    assert native.detected is True
    assert native.metadata["scale_basis"] == "embedded_dpi"
    assert placed.detected is False
    assert placed.metadata["scale_basis"] == "item_placement"


def test_ignores_sparse_noise_below_min_pixels_and_coverage():
    image = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
    for index in range(4):
        image.putpixel((10 + index * 20, 10), (0, 0, 0, 255))

    result = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=300,
        dpi_y=300,
        metadata={},
        probable_white_background=False,
    )
    image.close()

    assert result.detected is False
    assert result.metadata["pixel_count"] == 4


def test_skips_when_preview_cannot_resolve_half_millimeter():
    image = Image.new("RGBA", (40, 20), (0, 0, 0, 0))
    ImageDraw.Draw(image).line((2, 10, 38, 10), fill=(0, 0, 0, 255), width=1)

    result = AssetThinZoneAnalyzer().analyze(
        image=image,
        dpi_x=None,
        dpi_y=None,
        metadata={"page_width_in": 20, "page_height_in": 10},
        probable_white_background=False,
    )
    image.close()

    assert result.detected is False
    assert result.metadata["resolution_limited"] is True
    assert result.metadata["skip_reason"] == "insufficient_preview_resolution"
