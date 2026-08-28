"""Texte de composition sur planche : catalogue, validation et dessin vectoriel."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pymupdf
from django.conf import settings
from PIL import Image

MM_TO_POINTS = 72 / 25.4
MAX_TEXT_LENGTH = 200
MAX_TEXT_LINES = 20
DEFAULT_TEXT_CONTENT = "Votre texte"
DEFAULT_TEXT_FONT = "sans"
DEFAULT_TEXT_COLOR = "#1A1815"
DEFAULT_TEXT_ALIGN = "center"
DEFAULT_TEXT_SIZE_MM = Decimal("12.00")
MIN_TEXT_BOX_MM = Decimal("5.00")
MIN_TEXT_SIZE_MM = Decimal("2.00")
MAX_TEXT_SIZE_MM = Decimal("80.00")
TEXT_LINE_HEIGHT = 1.05
TEXT_PAD_X_EM = 0.18
TEXT_PAD_Y_EM = 0.12

FONT_CATALOG = {
    "sans": {
        "id": "sans",
        "label": "Helvetica",
        "pdf": "helv",
        "pdf_bold": "hebo",
        "css_family": "Helvetica, Arial, sans-serif",
    },
    "serif": {
        "id": "serif",
        "label": "Times",
        "pdf": "tiro",
        "pdf_bold": "tibo",
        "css_family": '"Times New Roman", Times, serif',
    },
    "mono": {
        "id": "mono",
        "label": "Courier",
        "pdf": "cour",
        "pdf_bold": "cobo",
        "css_family": '"Courier New", Courier, monospace',
    },
    "inter": {
        "id": "inter",
        "label": "Inter",
        "file": "inter-400.ttf",
        "file_bold": "inter-700.ttf",
        "css_family": '"Gang Inter", Helvetica, Arial, sans-serif',
    },
    "montserrat": {
        "id": "montserrat",
        "label": "Montserrat",
        "file": "montserrat-400.ttf",
        "file_bold": "montserrat-700.ttf",
        "css_family": '"Gang Montserrat", Helvetica, Arial, sans-serif',
    },
    "oswald": {
        "id": "oswald",
        "label": "Oswald",
        "file": "oswald-400.ttf",
        "file_bold": "oswald-700.ttf",
        "css_family": '"Gang Oswald", Helvetica, Arial, sans-serif',
    },
    "playfair": {
        "id": "playfair",
        "label": "Playfair",
        "file": "playfair-400.ttf",
        "file_bold": "playfair-700.ttf",
        "css_family": '"Gang Playfair", "Times New Roman", Times, serif',
    },
}

ALIGNMENTS = frozenset({"left", "center", "right"})
PDF_ALIGN = {"left": 0, "center": 1, "right": 2}
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class TextItemValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def serialized_font_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": spec["id"],
            "label": spec["label"],
            "css_family": spec["css_family"],
        }
        for spec in FONT_CATALOG.values()
    ]


def is_text_item(item) -> bool:
    return getattr(item, "kind", "") == "text" or (
        not getattr(item, "asset_version_id", None) and bool(getattr(item, "text_content", ""))
    )


def display_name(item) -> str:
    if is_text_item(item):
        first_line = (item.text_content or DEFAULT_TEXT_CONTENT).splitlines()[0].strip()
        return first_line[:48] or "Texte"
    version = getattr(item, "asset_version", None)
    asset = getattr(version, "asset", None)
    return getattr(asset, "name", None) or "Visuel"


def normalize_text_content(value) -> str:
    text = CONTROL_CHARS.sub("", str(value or "")).replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    text = text.strip(" \t")
    if not text.strip():
        raise TextItemValidationError("TEXT_REQUIRED", "Saisissez un texte à imprimer.")
    lines = text.split("\n")
    if len(lines) > MAX_TEXT_LINES:
        raise TextItemValidationError(
            "TEXT_TOO_LONG",
            f"Le texte est limité à {MAX_TEXT_LINES} lignes.",
        )
    if len(text) > MAX_TEXT_LENGTH:
        raise TextItemValidationError(
            "TEXT_TOO_LONG",
            f"Le texte est limité à {MAX_TEXT_LENGTH} caractères.",
        )
    return text


def normalize_text_font(value) -> str:
    font = str(value or DEFAULT_TEXT_FONT).strip().lower()
    if font not in FONT_CATALOG:
        raise TextItemValidationError("INVALID_TEXT_FONT", "Cette police n’est pas disponible.")
    return font


def normalize_text_color(value) -> str:
    color = str(value or DEFAULT_TEXT_COLOR).strip()
    if not HEX_COLOR.fullmatch(color):
        raise TextItemValidationError(
            "INVALID_TEXT_COLOR",
            "La couleur doit être un code hexadécimal #RRGGBB.",
        )
    return color.upper()


def normalize_text_align(value) -> str:
    align = str(value or DEFAULT_TEXT_ALIGN).strip().lower()
    if align not in ALIGNMENTS:
        raise TextItemValidationError(
            "INVALID_TEXT_ALIGN",
            "L’alignement doit être gauche, centré ou droite.",
        )
    return align


def normalize_text_bold(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, "", 0, "0", "false", "False"):
        return False
    if value in (1, "1", "true", "True", "on"):
        return True
    raise TextItemValidationError("INVALID_TEXT_WEIGHT", "Le graisse du texte est invalide.")


def normalize_text_size_mm(value) -> Decimal:
    if value in (None, ""):
        return DEFAULT_TEXT_SIZE_MM
    try:
        size = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise TextItemValidationError(
            "INVALID_TEXT_SIZE",
            "La taille du texte doit être un nombre en millimètres.",
        ) from error
    if size < MIN_TEXT_SIZE_MM or size > MAX_TEXT_SIZE_MM:
        raise TextItemValidationError(
            "INVALID_TEXT_SIZE",
            "La taille du texte doit être comprise entre 2 et 80 mm.",
        )
    return size


def font_spec(item) -> dict[str, str]:
    return FONT_CATALOG[normalize_text_font(getattr(item, "text_font", DEFAULT_TEXT_FONT))]


def _font_file(spec: dict, *, bold: bool) -> Path | None:
    filename = spec.get("file_bold") if bold and spec.get("file_bold") else spec.get("file")
    if not filename:
        return None
    candidates = [
        Path(settings.BASE_DIR) / "static_src" / "fonts" / "gang-sheet" / filename,
        Path(settings.STATIC_ROOT) / "fonts" / "gang-sheet" / filename,
    ]
    for path in candidates:
        if path.is_file():
            return path
    return candidates[0]


def font_resource(item) -> tuple[str, pymupdf.Font, Path | None]:
    spec = font_spec(item)
    bold = bool(getattr(item, "text_bold", False))
    path = _font_file(spec, bold=bold)
    if path is not None:
        name = f"gs{spec['id']}{'b' if bold else 'r'}"
        return name, pymupdf.Font(fontfile=str(path)), path
    name = spec["pdf_bold"] if bold else spec["pdf"]
    return name, pymupdf.Font(name), None


def register_page_font(page, item) -> str:
    name, _font, path = font_resource(item)
    if path is not None:
        page.insert_font(fontname=name, fontfile=str(path))
    return name


def pdf_color(item) -> tuple[float, float, float]:
    color = normalize_text_color(getattr(item, "text_color", DEFAULT_TEXT_COLOR))
    return (
        int(color[1:3], 16) / 255,
        int(color[3:5], 16) / 255,
        int(color[5:7], 16) / 255,
    )


def fontsize_pt(item) -> float:
    size_mm = float(getattr(item, "text_size_mm", None) or DEFAULT_TEXT_SIZE_MM)
    return max(4.0, min(size_mm * MM_TO_POINTS, 240.0))


def wrap_text_to_width(
    text: str, *, font: pymupdf.Font, fontsize: float, max_width_pt: float
) -> list[str]:
    usable = max(1.0, float(max_width_pt))
    lines: list[str] = []
    for paragraph in str(text or "").split("\n"):
        if paragraph == "":
            lines.append("")
            continue
        remaining = paragraph
        while remaining:
            if font.text_length(remaining, fontsize=fontsize) <= usable:
                lines.append(remaining)
                break
            lo, hi = 1, len(remaining)
            fit = 1
            while lo <= hi:
                mid = (lo + hi) // 2
                if font.text_length(remaining[:mid], fontsize=fontsize) <= usable:
                    fit = mid
                    lo = mid + 1
                else:
                    hi = mid - 1
            chunk = remaining[:fit]
            space = chunk.rfind(" ")
            if space > 0:
                lines.append(remaining[:space])
                remaining = remaining[space + 1 :]
            else:
                lines.append(chunk)
                remaining = remaining[fit:]
    return lines or [""]


def usable_text_max_width_mm(
    *,
    sheet_width_mm,
    margin_mm,
    x_mm=None,
    sheet_height_mm=None,
    y_mm=None,
    rotation=0,
) -> Decimal:
    margin = max(Decimal("0.00"), Decimal(margin_mm))
    quarter = int(rotation or 0) % 360 in {90, 270}
    if quarter:
        limit = max(
            MIN_TEXT_BOX_MM,
            Decimal(sheet_height_mm if sheet_height_mm is not None else sheet_width_mm),
        )
        origin = y_mm
    else:
        limit = max(MIN_TEXT_BOX_MM, Decimal(sheet_width_mm))
        origin = x_mm
    usable = max(MIN_TEXT_BOX_MM, limit - (margin * 2))
    if origin is None:
        return usable.quantize(Decimal("0.01"))
    remaining = max(MIN_TEXT_BOX_MM, limit - Decimal(origin) - margin)
    return min(usable, remaining).quantize(Decimal("0.01"))


def fitted_box_mm(
    *, content, max_width_mm, font=None, bold=False, size_mm=None
) -> tuple[Decimal, Decimal]:
    text = content or DEFAULT_TEXT_CONTENT
    max_width = max(MIN_TEXT_BOX_MM, Decimal(max_width_mm))
    size = normalize_text_size_mm(size_mm if size_mm is not None else DEFAULT_TEXT_SIZE_MM)
    dummy = type(
        "TextMeasure",
        (),
        {"width_mm": max_width, "text_font": font, "text_bold": bold, "text_size_mm": size},
    )()
    _name, measure_font, _path = font_resource(dummy)
    fontsize = fontsize_pt(dummy)
    pad_x_pt = 2 * TEXT_PAD_X_EM * fontsize
    inner_max_pt = max(1.0, float(max_width) * MM_TO_POINTS - pad_x_pt)
    lines = wrap_text_to_width(
        text,
        font=measure_font,
        fontsize=fontsize,
        max_width_pt=inner_max_pt,
    )
    longest_pt = 0.0
    for line in lines:
        if line:
            longest_pt = max(longest_pt, measure_font.text_length(line, fontsize=fontsize))
    width_mm = Decimal(str((longest_pt + pad_x_pt) / MM_TO_POINTS))
    width_mm = max(MIN_TEXT_BOX_MM, min(max_width, width_mm)).quantize(Decimal("0.01"))
    height_pt = (len(lines) * fontsize * TEXT_LINE_HEIGHT) + (2 * TEXT_PAD_Y_EM * fontsize)
    height_mm = max(MIN_TEXT_BOX_MM, Decimal(str(height_pt / MM_TO_POINTS))).quantize(
        Decimal("0.01")
    )
    return width_mm, height_mm


def fitted_height_mm(*, content, width_mm, font=None, bold=False, size_mm=None) -> Decimal:
    _width, height = fitted_box_mm(
        content=content,
        max_width_mm=width_mm,
        font=font,
        bold=bold,
        size_mm=size_mm,
    )
    return height


def _textbox_unused_height(rect, text, *, item, fontsize, align, rotate) -> float:
    document = pymupdf.open()
    try:
        width = max(2.0, float(rect.width))
        height = max(2.0, float(rect.height))
        page = document.new_page(width=width, height=height)
        fontname = register_page_font(page, item)
        return page.insert_textbox(
            page.rect,
            text,
            fontsize=fontsize,
            fontname=fontname,
            align=align,
            rotate=rotate,
        )
    finally:
        document.close()


def fitted_fontsize(item, rect) -> float:
    text = getattr(item, "text_content", "") or DEFAULT_TEXT_CONTENT
    align = PDF_ALIGN[normalize_text_align(getattr(item, "text_align", DEFAULT_TEXT_ALIGN))]
    size = fontsize_pt(item)
    min_size = 4.0
    unused = _textbox_unused_height(
        rect,
        text,
        item=item,
        fontsize=size,
        align=align,
        rotate=0,
    )
    while unused < 0 and size > min_size:
        size = max(min_size, size * 0.82)
        unused = _textbox_unused_height(
            rect,
            text,
            item=item,
            fontsize=size,
            align=align,
            rotate=0,
        )
    return size


def default_box_mm(
    *,
    sheet_width_mm,
    margin_mm,
    content=DEFAULT_TEXT_CONTENT,
    font=DEFAULT_TEXT_FONT,
    bold=False,
    size_mm=DEFAULT_TEXT_SIZE_MM,
) -> tuple[Decimal, Decimal]:
    max_width = usable_text_max_width_mm(
        sheet_width_mm=sheet_width_mm,
        margin_mm=margin_mm,
    )
    return fitted_box_mm(
        content=content,
        max_width_mm=max_width,
        font=font,
        bold=bold,
        size_mm=size_mm,
    )


def default_origin_mm(*, sheet, width_mm, height_mm) -> tuple[Decimal, Decimal]:
    margin = Decimal(sheet.margin_mm)
    usable_width = Decimal(sheet.width_mm) - (margin * 2)
    usable_height = Decimal(sheet.height_mm) - (margin * 2)
    x = margin + max(Decimal("0.00"), (usable_width - Decimal(width_mm)) / 2)
    offset_y = min(Decimal("20.00"), (usable_height - Decimal(height_mm)) / 2)
    y = margin + max(Decimal("0.00"), offset_y)
    return x.quantize(Decimal("0.01")), y.quantize(Decimal("0.01"))


def _fill_textbox(*, page, item, rect) -> None:
    text = getattr(item, "text_content", "") or DEFAULT_TEXT_CONTENT
    fontname = register_page_font(page, item)
    page.insert_textbox(
        rect,
        text,
        fontsize=fitted_fontsize(item, rect),
        fontname=fontname,
        color=pdf_color(item),
        align=PDF_ALIGN[normalize_text_align(getattr(item, "text_align", DEFAULT_TEXT_ALIGN))],
        rotate=0,
        overlay=True,
    )


def draw_text_item(*, page, item, rect, rotate=None) -> None:
    rotation = int(item.rotation if rotate is None else rotate) % 360
    if rotation not in {90, 180, 270}:
        _fill_textbox(page=page, item=item, rect=rect)
        return
    width_pt = max(2.0, float(item.width_mm) * MM_TO_POINTS)
    height_pt = max(2.0, float(item.height_mm) * MM_TO_POINTS)
    document = pymupdf.open()
    try:
        source = document.new_page(width=width_pt, height=height_pt)
        _fill_textbox(page=source, item=item, rect=source.rect)
        page.show_pdf_page(
            rect,
            document,
            0,
            keep_proportion=False,
            overlay=True,
            rotate=rotation,
        )
    finally:
        document.close()


def rasterize_text_item(*, item, target_width: int, target_height: int) -> Image.Image:
    width_pt = max(1.0, float(item.width_mm) * MM_TO_POINTS)
    height_pt = max(1.0, float(item.height_mm) * MM_TO_POINTS)
    document = pymupdf.open()
    try:
        page = document.new_page(width=width_pt, height=height_pt)
        draw_text_item(page=page, item=item, rect=page.rect, rotate=0)
        zoom_x = max(1, int(target_width)) / width_pt
        zoom_y = max(1, int(target_height)) / height_pt
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(zoom_x, zoom_y),
            colorspace=pymupdf.csRGB,
            alpha=True,
            annots=False,
        )
        image = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.close()
    if image.size != (max(1, target_width), max(1, target_height)):
        resized = image.resize(
            (max(1, target_width), max(1, target_height)),
            Image.Resampling.LANCZOS,
        )
        image.close()
        return resized
    return image
