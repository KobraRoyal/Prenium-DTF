from __future__ import annotations

import json
from contextlib import suppress
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import ceil, floor
from statistics import median

import pymupdf
from django.core.exceptions import ValidationError
from PIL import Image, ImageChops, UnidentifiedImageError

from apps.uploads.services.asset_preview import AssetPreviewError, AssetPreviewRenderer
from apps.uploads.services.validation import UploadValidationService

CROP_PRECISION = Decimal("0.000001")
MIN_CROP_SIZE = Decimal("0.01")
ONE = Decimal("1")
ZERO = Decimal("0")
MAX_CROP_MANIFEST_CHARS = 16_384
AUTO_CROP_MAX_SIDE = 2_048
AUTO_CROP_BACKGROUND_TOLERANCE = 18
AUTO_CROP_VECTOR_PADDING = Decimal("0.0025")
CROP_MODE_MANUAL = "manual"
CROP_MODE_AUTO = "auto"
VALID_CROP_MODES = frozenset({CROP_MODE_MANUAL, CROP_MODE_AUTO})


class CropValidationError(ValueError):
    pass


class AutoCropError(ValueError):
    pass


@dataclass(frozen=True)
class CropBox:
    """Fenêtre de recadrage normalisée, indépendante du format source."""

    x: Decimal = ZERO
    y: Decimal = ZERO
    width: Decimal = ONE
    height: Decimal = ONE

    @classmethod
    def full(cls) -> CropBox:
        return cls()

    @classmethod
    def from_values(cls, *, x=ZERO, y=ZERO, width=ONE, height=ONE) -> CropBox:
        values = {
            "x": cls._decimal(x, "x"),
            "y": cls._decimal(y, "y"),
            "width": cls._decimal(width, "largeur"),
            "height": cls._decimal(height, "hauteur"),
        }
        crop = cls(**values)
        crop.validate()
        return crop

    @classmethod
    def from_source_asset(cls, source_asset) -> CropBox:
        return cls.from_values(
            x=source_asset.crop_x,
            y=source_asset.crop_y,
            width=source_asset.crop_width,
            height=source_asset.crop_height,
        )

    @staticmethod
    def _decimal(value, label: str) -> Decimal:
        if isinstance(value, bool):
            raise CropValidationError(f"La valeur de crop « {label} » est invalide.")
        try:
            parsed = Decimal(str(value)).quantize(CROP_PRECISION)
        except (InvalidOperation, TypeError, ValueError) as error:
            raise CropValidationError(f"La valeur de crop « {label} » est invalide.") from error
        if not parsed.is_finite():
            raise CropValidationError(f"La valeur de crop « {label} » est invalide.")
        return parsed

    def validate(self) -> None:
        if self.x < ZERO or self.y < ZERO:
            raise CropValidationError("Le recadrage doit rester dans le visuel.")
        if self.width < MIN_CROP_SIZE or self.height < MIN_CROP_SIZE:
            raise CropValidationError("Le recadrage est trop petit.")
        if self.x + self.width > ONE or self.y + self.height > ONE:
            raise CropValidationError("Le recadrage dépasse les limites du visuel.")

    @property
    def is_full(self) -> bool:
        return self.x == ZERO and self.y == ZERO and self.width == ONE and self.height == ONE

    def dimensions(self, *, width, height) -> tuple[Decimal, Decimal]:
        return (
            (Decimal(width) * self.width).quantize(Decimal("0.01")),
            (Decimal(height) * self.height).quantize(Decimal("0.01")),
        )

    def pixel_box(self, *, width: int, height: int) -> tuple[int, int, int, int]:
        left = max(0, floor(float(self.x) * width))
        top = max(0, floor(float(self.y) * height))
        right = min(width, ceil(float(self.x + self.width) * width))
        bottom = min(height, ceil(float(self.y + self.height) * height))
        if right <= left or bottom <= top:
            raise CropValidationError("Le recadrage ne contient aucun pixel.")
        return left, top, right, bottom

    def to_metadata(self) -> dict[str, str]:
        return {
            "x": str(self.x),
            "y": str(self.y),
            "width": str(self.width),
            "height": str(self.height),
        }


@dataclass(frozen=True)
class CropInstruction:
    mode: str
    crop: CropBox


@dataclass(frozen=True)
class AutoCropResult:
    crop: CropBox
    content_kind: str
    basis: str

    def to_metadata(self) -> dict[str, object]:
        return {
            "content_kind": self.content_kind,
            "basis": self.basis,
            "crop": self.crop.to_metadata(),
        }


class AutoCropService:
    """Calcule un crop de contenu sans modifier ni rasteriser la source."""

    vector_kinds = frozenset(
        {
            "fill-path",
            "stroke-path",
            "fill-text",
            "stroke-text",
            "fill-shade",
            "stroke-shade",
        }
    )

    def __init__(self, *, validator=None, preview_renderer=None):
        self.validator = validator or UploadValidationService()
        self.preview_renderer = preview_renderer or AssetPreviewRenderer()

    def detect(self, uploaded_file) -> AutoCropResult:
        try:
            validated = self.validator.validate_uploaded_file(uploaded_file)
            content = self._read_uploaded_file(validated.uploaded_file)
            if validated.mime_type == "application/pdf" or content.lstrip().startswith(b"%PDF-"):
                return self._detect_pdf(content)
            rendered = self.preview_renderer.render_content(
                content=content,
                original_filename=validated.original_filename,
                mime_type=validated.mime_type,
            )
            try:
                crop = self._detect_image(rendered.image)
                has_vector = bool(rendered.metadata.get("has_vector_artwork"))
                has_raster = bool(rendered.metadata.get("has_raster_artwork"))
                if not has_vector:
                    has_raster = True
                return AutoCropResult(
                    crop=crop,
                    content_kind=self._content_kind(
                        has_vector=has_vector,
                        has_raster=has_raster,
                    ),
                    basis="rendered_content" if has_vector else "visible_pixels",
                )
            finally:
                rendered.image.close()
        except AutoCropError:
            raise
        except (
            AssetPreviewError,
            OSError,
            RuntimeError,
            UnidentifiedImageError,
            ValidationError,
        ) as error:
            raise AutoCropError(
                "Le contenu de ce fichier ne permet pas un recadrage automatique fiable."
            ) from error

    @staticmethod
    def _read_uploaded_file(uploaded_file) -> bytes:
        position = None
        with suppress(AttributeError, OSError, ValueError):
            position = uploaded_file.tell()
        try:
            uploaded_file.seek(0)
            content = bytes(uploaded_file.read() or b"")
        except (AttributeError, OSError, ValueError) as error:
            raise AutoCropError(
                "Le fichier ne peut pas être lu pour le recadrage automatique."
            ) from error
        finally:
            with suppress(AttributeError, OSError, ValueError):
                uploaded_file.seek(position if position is not None else 0)
        if not content:
            raise AutoCropError("Le fichier est vide.")
        return content

    def _detect_pdf(self, content: bytes) -> AutoCropResult:
        try:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                if document.page_count < 1:
                    raise AutoCropError("Le document ne contient aucune page.")
                page = document.load_page(0)
                page_rect = page.rect
                content_rect = None
                has_vector = False
                has_raster = False
                for entry in page.get_bboxlog():
                    kind, bbox = entry[:2]
                    if kind in self.vector_kinds:
                        has_vector = True
                    elif "image" in kind:
                        has_raster = True
                    else:
                        continue
                    content_rect = self._include_pdf_rect(content_rect, bbox, page_rect)
                for image_info in page.get_image_info(xrefs=True):
                    bbox = image_info.get("bbox")
                    if bbox:
                        has_raster = True
                        content_rect = self._include_pdf_rect(content_rect, bbox, page_rect)
                crop = self._crop_from_pdf_rect(content_rect, page_rect)
                return AutoCropResult(
                    crop=crop,
                    content_kind=self._content_kind(
                        has_vector=has_vector,
                        has_raster=has_raster,
                    ),
                    basis="native_pdf_objects",
                )
        except AutoCropError:
            raise
        except (RuntimeError, TypeError, ValueError) as error:
            raise AutoCropError("Le document vectoriel ne peut pas être analysé.") from error

    @staticmethod
    def _include_pdf_rect(current, bbox, page_rect):
        try:
            candidate = pymupdf.Rect(bbox) & page_rect
        except (RuntimeError, TypeError, ValueError):
            return current
        if (
            candidate.is_empty
            or candidate.is_infinite
            or candidate.width <= 0
            or candidate.height <= 0
        ):
            return current
        if current is None:
            return pymupdf.Rect(candidate)
        current.include_rect(candidate)
        return current

    @classmethod
    def _crop_from_pdf_rect(cls, content_rect, page_rect) -> CropBox:
        if content_rect is None or page_rect.width <= 0 or page_rect.height <= 0:
            return CropBox.full()
        x0 = Decimal(str((content_rect.x0 - page_rect.x0) / page_rect.width))
        y0 = Decimal(str((content_rect.y0 - page_rect.y0) / page_rect.height))
        x1 = Decimal(str((content_rect.x1 - page_rect.x0) / page_rect.width))
        y1 = Decimal(str((content_rect.y1 - page_rect.y0) / page_rect.height))
        return cls._crop_from_intervals(
            x0 - AUTO_CROP_VECTOR_PADDING,
            y0 - AUTO_CROP_VECTOR_PADDING,
            x1 + AUTO_CROP_VECTOR_PADDING,
            y1 + AUTO_CROP_VECTOR_PADDING,
        )

    @classmethod
    def _detect_image(cls, image: Image.Image) -> CropBox:
        sample = image.convert("RGBA")
        try:
            sample.thumbnail(
                (AUTO_CROP_MAX_SIDE, AUTO_CROP_MAX_SIDE),
                Image.Resampling.LANCZOS,
            )
            alpha = sample.getchannel("A")
            try:
                alpha_min, _alpha_max = alpha.getextrema()
                if alpha_min < 250:
                    mask = alpha.point(lambda value: 255 if value > 3 else 0)
                else:
                    mask = cls._opaque_content_mask(sample)
            finally:
                alpha.close()
            try:
                bbox = mask.getbbox()
            finally:
                mask.close()
            if bbox is None:
                return CropBox.full()
            left, top, right, bottom = bbox
            padding = 2
            return cls._crop_from_intervals(
                Decimal(max(0, left - padding)) / Decimal(sample.width),
                Decimal(max(0, top - padding)) / Decimal(sample.height),
                Decimal(min(sample.width, right + padding)) / Decimal(sample.width),
                Decimal(min(sample.height, bottom + padding)) / Decimal(sample.height),
            )
        finally:
            sample.close()

    @staticmethod
    def _opaque_content_mask(image: Image.Image) -> Image.Image:
        rgb = image.convert("RGB")
        try:
            width, height = rgb.size
            border = []
            for x in range(width):
                border.append(rgb.getpixel((x, 0)))
                if height > 1:
                    border.append(rgb.getpixel((x, height - 1)))
            for y in range(1, max(1, height - 1)):
                border.append(rgb.getpixel((0, y)))
                if width > 1:
                    border.append(rgb.getpixel((width - 1, y)))
            background_color = tuple(
                round(median(pixel[channel] for pixel in border)) for channel in range(3)
            )
            background = Image.new("RGB", rgb.size, background_color)
            try:
                difference = ImageChops.difference(rgb, background)
            finally:
                background.close()
            try:
                red, green, blue = difference.split()
                red_green = ImageChops.lighter(red, green)
                maximum = ImageChops.lighter(red_green, blue)
                red_green.close()
                red.close()
                green.close()
                blue.close()
            finally:
                difference.close()
            return maximum.point(lambda value: 255 if value > AUTO_CROP_BACKGROUND_TOLERANCE else 0)
        finally:
            rgb.close()

    @staticmethod
    def _content_kind(*, has_vector: bool, has_raster: bool) -> str:
        if has_vector and has_raster:
            return "mixed"
        if has_vector:
            return "vector"
        return "raster"

    @staticmethod
    def _crop_from_intervals(x0: Decimal, y0: Decimal, x1: Decimal, y1: Decimal) -> CropBox:
        x0, x1 = AutoCropService._bounded_interval(x0, x1)
        y0, y1 = AutoCropService._bounded_interval(y0, y1)
        return CropBox.from_values(x=x0, y=y0, width=x1 - x0, height=y1 - y0)

    @staticmethod
    def _bounded_interval(start: Decimal, end: Decimal) -> tuple[Decimal, Decimal]:
        start = max(ZERO, min(ONE, start))
        end = max(ZERO, min(ONE, end))
        if end - start >= MIN_CROP_SIZE:
            return start, end
        center = (start + end) / 2
        start = max(ZERO, center - MIN_CROP_SIZE / 2)
        end = min(ONE, start + MIN_CROP_SIZE)
        start = max(ZERO, end - MIN_CROP_SIZE)
        return start, end


def crop_image(image: Image.Image, crop: CropBox) -> Image.Image:
    if crop.is_full:
        return image.copy()
    return image.crop(crop.pixel_box(width=image.width, height=image.height))


def parse_crop_manifest(raw_manifest: str, *, file_count: int) -> dict[int, CropInstruction]:
    if not raw_manifest:
        return {}
    if len(raw_manifest) > MAX_CROP_MANIFEST_CHARS:
        raise CropValidationError("Les données de recadrage sont trop volumineuses.")
    try:
        payload = json.loads(raw_manifest)
    except json.JSONDecodeError as error:
        raise CropValidationError("Les données de recadrage sont invalides.") from error
    if not isinstance(payload, list) or len(payload) > file_count:
        raise CropValidationError("Les données de recadrage ne correspondent pas aux fichiers.")

    crops: dict[int, CropInstruction] = {}
    for entry in payload:
        if not isinstance(entry, dict) or isinstance(entry.get("index"), bool):
            raise CropValidationError("Une entrée de recadrage est invalide.")
        try:
            index = int(entry.get("index"))
        except (TypeError, ValueError) as error:
            raise CropValidationError("Un index de recadrage est invalide.") from error
        if index < 0 or index >= file_count or index in crops:
            raise CropValidationError("Un index de recadrage est invalide.")
        mode = entry.get("mode", CROP_MODE_MANUAL)
        if not isinstance(mode, str) or mode not in VALID_CROP_MODES:
            raise CropValidationError("Le mode de recadrage est invalide.")
        crops[index] = CropInstruction(
            mode=mode,
            crop=CropBox.from_values(
                x=entry.get("x", ZERO),
                y=entry.get("y", ZERO),
                width=entry.get("width", ONE),
                height=entry.get("height", ONE),
            ),
        )
    return crops
