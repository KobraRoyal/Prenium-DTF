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
