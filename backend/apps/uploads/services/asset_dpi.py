from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from PIL import Image


@dataclass(frozen=True)
class SourceMetrics:
    width_px: int | None = None
    height_px: int | None = None
    dpi_x: float | None = None
    dpi_y: float | None = None
    page_width_in: float | None = None
    page_height_in: float | None = None
    display_width_in: float | None = None
    display_height_in: float | None = None
    placement_width_in: float | None = None
    placement_height_in: float | None = None
    placement_effective_dpi: float | None = None
    artboard_width_mm: float | None = None
    artboard_height_mm: float | None = None
    uses_artboard_dimensions: bool = False
    dpi_source: str | None = None
    dimension_basis: str = "pixels"


def positive_dpi(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return round(parsed, 2) if parsed > 0 else None


def extract_pillow_dpi(image: Image.Image) -> tuple[float | None, float | None]:
    exif_dpi = _dpi_from_exif(image)
    if exif_dpi != (None, None):
        return exif_dpi

    tag_dpi = _dpi_from_tag_v2(image)
    if tag_dpi != (None, None):
        return tag_dpi

    info_dpi = image.info.get("dpi")
    if info_dpi:
        dpi_x = positive_dpi(info_dpi[0] if len(info_dpi) > 0 else None)
        dpi_y = positive_dpi(info_dpi[1] if len(info_dpi) > 1 else dpi_x)
        if dpi_x and dpi_y:
            return dpi_x, dpi_y

    jfif_dpi = _dpi_from_jfif(image)
    if jfif_dpi != (None, None):
        return jfif_dpi

    return None, None


def extract_pillow_source_metrics(image: Image.Image) -> SourceMetrics:
    width_px, height_px = image.size
    dpi_x, dpi_y = extract_pillow_dpi(image)
    dpi_source = "embedded" if dpi_x and dpi_y else None
    display_width_in = None
    display_height_in = None
    if dpi_x and dpi_y and width_px and height_px:
        display_width_in = width_px / dpi_x
        display_height_in = height_px / dpi_y
    return SourceMetrics(
        width_px=int(width_px),
        height_px=int(height_px),
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        display_width_in=display_width_in,
        display_height_in=display_height_in,
        dpi_source=dpi_source,
        dimension_basis="pixels",
    )


def extract_psd_source_metrics(document) -> SourceMetrics:
    from psd_tools.constants import Resource

    dpi_x = dpi_y = None
    resolution = document.image_resources.get_data(Resource.RESOLUTION_INFO)
    if resolution is not None:
        if int(getattr(resolution, "horizontal_unit", 0) or 0) == 1:
            dpi_x = positive_dpi(getattr(resolution, "horizontal", 0) / 65536.0)
        if int(getattr(resolution, "vertical_unit", 0) or 0) == 1:
            dpi_y = positive_dpi(getattr(resolution, "vertical", 0) / 65536.0)
        if dpi_x and dpi_y is None:
            dpi_y = dpi_x
        if dpi_y and dpi_x is None:
            dpi_x = dpi_y

    width_px = int(document.width)
    height_px = int(document.height)
    display_width_in = None
    display_height_in = None
    if dpi_x and dpi_y:
        display_width_in = width_px / dpi_x
        display_height_in = height_px / dpi_y

    return SourceMetrics(
        width_px=width_px,
        height_px=height_px,
        dpi_x=dpi_x,
        dpi_y=dpi_y,
        display_width_in=display_width_in,
        display_height_in=display_height_in,
        dpi_source="embedded" if dpi_x and dpi_y else None,
        dimension_basis="pixels",
    )


def extract_pdf_source_metrics(document, page) -> SourceMetrics:
    page_width_in = float(page.rect.width) / 72.0
    page_height_in = float(page.rect.height) / 72.0
    info_by_xref = {
        int(info["xref"]): info
        for info in page.get_image_info(xrefs=True)
        if info.get("xref")
    }

    best: SourceMetrics | None = None
    best_score = 0

    for image_entry in page.get_images(full=True):
        xref = int(image_entry[0])
        try:
            extracted = document.extract_image(xref)
        except (RuntimeError, TypeError, ValueError):
            continue

        pixel_w = int(extracted.get("width") or 0)
        pixel_h = int(extracted.get("height") or 0)
        if pixel_w <= 0 or pixel_h <= 0:
            continue

        embedded_dpi_x = embedded_dpi_y = None
        image_bytes = extracted.get("image")
        if image_bytes:
            try:
                with Image.open(BytesIO(image_bytes)) as embedded_image:
                    embedded_dpi_x, embedded_dpi_y = extract_pillow_dpi(embedded_image)
            except (OSError, ValueError):
                embedded_dpi_x = embedded_dpi_y = None

        placement_w_in, placement_h_in = _pdf_image_placement_inches(
            page,
            xref,
            info_by_xref.get(xref),
        )
        placement_effective_dpi = None
        if placement_w_in and placement_h_in:
            placement_effective_dpi = positive_dpi(
                min(pixel_w / placement_w_in, pixel_h / placement_h_in)
            )

        if embedded_dpi_x and embedded_dpi_y:
            dpi_x = embedded_dpi_x
            dpi_y = embedded_dpi_y
            dpi_source = "embedded"
            display_w_in = pixel_w / dpi_x
            display_h_in = pixel_h / dpi_y
        elif placement_effective_dpi:
            dpi_x = dpi_y = placement_effective_dpi
            dpi_source = "effective"
            display_w_in = placement_w_in
            display_h_in = placement_h_in
        else:
            continue

        score = pixel_w * pixel_h
        if score <= best_score:
            continue

        best_score = score
        best = SourceMetrics(
            width_px=pixel_w,
            height_px=pixel_h,
            dpi_x=dpi_x,
            dpi_y=dpi_y,
            page_width_in=page_width_in,
            page_height_in=page_height_in,
            display_width_in=display_w_in,
            display_height_in=display_h_in,
            placement_width_in=placement_w_in,
            placement_height_in=placement_h_in,
            placement_effective_dpi=placement_effective_dpi,
            dpi_source=dpi_source,
            dimension_basis="pixels",
        )

    if best is not None:
        artboard_width_mm, artboard_height_mm = extract_pdf_artboard_size_mm(document, page)
        uses_artboard = should_use_pdf_artboard_dimensions(page, best)
        return SourceMetrics(
            width_px=best.width_px,
            height_px=best.height_px,
            dpi_x=best.dpi_x,
            dpi_y=best.dpi_y,
            page_width_in=best.page_width_in,
            page_height_in=best.page_height_in,
            display_width_in=best.display_width_in,
            display_height_in=best.display_height_in,
            placement_width_in=best.placement_width_in,
            placement_height_in=best.placement_height_in,
            placement_effective_dpi=best.placement_effective_dpi,
            artboard_width_mm=artboard_width_mm,
            artboard_height_mm=artboard_height_mm,
            uses_artboard_dimensions=uses_artboard,
            dpi_source=best.dpi_source,
            dimension_basis="page" if uses_artboard else best.dimension_basis,
        )

    artboard_width_mm, artboard_height_mm = extract_pdf_artboard_size_mm(document, page)
    return SourceMetrics(
        width_px=max(int(round(page.rect.width)), 1),
        height_px=max(int(round(page.rect.height)), 1),
        dpi_x=None,
        dpi_y=None,
        page_width_in=page_width_in,
        page_height_in=page_height_in,
        artboard_width_mm=artboard_width_mm,
        artboard_height_mm=artboard_height_mm,
        dimension_basis="page",
    )


def extract_pdf_artboard_size_mm(document, page) -> tuple[float, float]:
    """Return print size in mm aligned with the import preview (PDF.js MediaBox).

    Illustrator XMP MaxPageSize is often a legacy artboard (e.g. 20 in) that no longer
    matches the page MediaBox shown in the verify-import dialog. When XMP and MediaBox
    disagree, MediaBox wins so analysis matches what the client already displayed.
    """
    media_width_mm = round(float(page.rect.width) / 72.0 * 25.4, 2)
    media_height_mm = round(float(page.rect.height) / 72.0 * 25.4, 2)

    xmp_size = _parse_xmp_max_page_size_mm(document.get_xml_metadata() or "")
    if xmp_size is None:
        return media_width_mm, media_height_mm

    xmp_width_mm, xmp_height_mm = xmp_size
    if _pdf_dimensions_agree(
        xmp_width_mm,
        xmp_height_mm,
        media_width_mm,
        media_height_mm,
        tolerance=0.15,
    ):
        return round(xmp_width_mm, 2), round(xmp_height_mm, 2)
    return media_width_mm, media_height_mm


def _parse_xmp_max_page_size_mm(xmp: str) -> tuple[float, float] | None:
    match = re.search(
        r"xmpTPg:MaxPageSize[\s\S]{0,800}?"
        r"(?:stDim:w=\"([\d.]+)\"|<stDim:w>([\d.]+)</stDim:w>)[\s\S]{0,300}?"
        r"(?:stDim:h=\"([\d.]+)\"|<stDim:h>([\d.]+)</stDim:h>)[\s\S]{0,300}?"
        r"(?:stDim:unit=\"([A-Za-z]+)\"|<stDim:unit>([A-Za-z]+)</stDim:unit>|"
        r"(Millimeters|Inches|Centimeters))",
        xmp,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None

    width_raw = match.group(1) or match.group(2)
    height_raw = match.group(3) or match.group(4)
    unit = (match.group(5) or match.group(6) or match.group(7) or "").lower()
    if not width_raw or not height_raw or not unit:
        return None

    width = float(width_raw)
    height = float(height_raw)
    if unit == "inches":
        width *= 25.4
        height *= 25.4
    elif unit == "centimeters":
        width *= 10.0
        height *= 10.0
    elif unit != "millimeters":
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _pdf_dimensions_agree(
    width_a: float,
    height_a: float,
    width_b: float,
    height_b: float,
    *,
    tolerance: float,
) -> bool:
    if width_a <= 0 or height_a <= 0 or width_b <= 0 or height_b <= 0:
        return False
    return (
        abs(width_a - width_b) / width_b <= tolerance
        and abs(height_a - height_b) / height_b <= tolerance
    )


def pdf_page_has_vector_artwork(page) -> bool:
    vector_kinds = {
        "fill-path",
        "stroke-path",
        "fill-text",
        "stroke-text",
        "fill-shade",
        "stroke-shade",
    }
    for kind, _bbox in page.get_bboxlog():
        if kind in vector_kinds:
            return True
    try:
        return bool(page.get_drawings())
    except (RuntimeError, TypeError, ValueError):
        return False


def should_use_pdf_artboard_dimensions(page, source_metrics: SourceMetrics) -> bool:
    """Prefer MediaBox/artboard for print layout size.

    Intrinsic embedded DPI (pixels ÷ tag) often describes the source file, not the
    size at which the image is placed on the PDF page. For DTF we must follow the
    page geometry shown in the import preview whenever the artwork fills most of
    the page, including raster-only PDFs.
    """
    page_area = (source_metrics.page_width_in or 0) * (source_metrics.page_height_in or 0)
    placement_w = source_metrics.placement_width_in
    placement_h = source_metrics.placement_height_in
    if not placement_w or not placement_h or page_area <= 0:
        return True

    placement_area = placement_w * placement_h
    if placement_area <= 0:
        return True

    coverage = placement_area / page_area
    # Raster (nearly) full-page → align with PDF.js / MediaBox preview.
    if coverage >= (2.0 / 3.0):
        return True

    # Illustrator-style mixed docs: large page with a partial photo + vectors.
    if pdf_page_has_vector_artwork(page) and (page_area / placement_area) > 1.5:
        return True

    return False


def parse_eps_page_size_inches(content: bytes) -> tuple[float, float] | None:
    try:
        header = content[:8192].decode("latin-1", errors="ignore")
    except UnicodeDecodeError:
        return None

    match = re.search(
        r"%%BoundingBox:\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)",
        header,
    )
    if match is None:
        return None

    x0, y0, x1, y1 = (float(value) for value in match.groups())
    width_in = abs(x1 - x0) / 72.0
    height_in = abs(y1 - y0) / 72.0
    if width_in <= 0 or height_in <= 0:
        return None
    return width_in, height_in


def _pdf_image_placement_inches(page, xref: int, info=None) -> tuple[float | None, float | None]:
    try:
        rects = page.get_image_rects(xref)
    except (RuntimeError, TypeError, ValueError):
        rects = []
    if rects:
        rect = max(rects, key=lambda candidate: abs(candidate.width) * abs(candidate.height))
        width_in = abs(float(rect.width)) / 72.0
        height_in = abs(float(rect.height)) / 72.0
        if width_in > 0 and height_in > 0:
            return width_in, height_in

    if info and info.get("bbox") and len(info["bbox"]) >= 4:
        bbox = info["bbox"]
        width_in = abs(float(bbox[2]) - float(bbox[0])) / 72.0
        height_in = abs(float(bbox[3]) - float(bbox[1])) / 72.0
        if width_in > 0 and height_in > 0:
            return width_in, height_in

    return None, None


def _dpi_from_exif(image: Image.Image) -> tuple[float | None, float | None]:
    try:
        exif = image.getexif()
    except (AttributeError, OSError, ValueError):
        return None, None
    if not exif:
        return None, None

    dpi_x = _resolution_tag_to_dpi(exif.get(282), exif.get(296))
    dpi_y = _resolution_tag_to_dpi(exif.get(283), exif.get(296))
    if dpi_x and dpi_y:
        return dpi_x, dpi_y
    return None, None


def _dpi_from_tag_v2(image: Image.Image) -> tuple[float | None, float | None]:
    tag_v2 = getattr(image, "tag_v2", None)
    if tag_v2 is None:
        return None, None

    unit = tag_v2.get(296)
    dpi_x = _resolution_tag_to_dpi(tag_v2.get(282), unit)
    dpi_y = _resolution_tag_to_dpi(tag_v2.get(283), unit)
    if dpi_x and dpi_y:
        return dpi_x, dpi_y
    return None, None


def _dpi_from_jfif(image: Image.Image) -> tuple[float | None, float | None]:
    density = image.info.get("jfif_density")
    unit = image.info.get("jfif_unit")
    if not density or unit != 1:
        return None, None
    dpi_x = positive_dpi(density[0] if len(density) > 0 else None)
    dpi_y = positive_dpi(density[1] if len(density) > 1 else dpi_x)
    if dpi_x and dpi_y:
        return dpi_x, dpi_y
    return None, None


def _resolution_tag_to_dpi(value, unit) -> float | None:
    if value is None:
        return None

    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        if value.denominator == 0:
            return None
        resolution = float(value.numerator) / float(value.denominator)
    elif isinstance(value, tuple) and len(value) == 2:
        numerator, denominator = value
        if denominator == 0:
            return None
        resolution = float(numerator) / float(denominator)
    else:
        resolution = positive_dpi(value)
        if resolution is None:
            return None

    if unit == 3:
        return positive_dpi(resolution * 2.54)
    return positive_dpi(resolution)
