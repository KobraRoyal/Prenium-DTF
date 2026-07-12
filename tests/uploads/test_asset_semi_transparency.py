from io import BytesIO

from apps.uploads.services.asset_semi_transparency import AssetSemiTransparencyAnalyzer
from PIL import Image, ImageDraw


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
