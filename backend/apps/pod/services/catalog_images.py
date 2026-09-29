from __future__ import annotations

from io import BytesIO
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
FULL_MAX_EDGE = 1200
THUMB_MAX_EDGE = 160


def shopify_cdn_resized(url: str, *, width: int = 96) -> str:
    """Resize via CDN Shopify (pas de re-téléchargement local)."""
    raw = (url or "").strip()
    if not raw or width <= 0:
        return raw
    parts = urlsplit(raw)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["width"] = str(width)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def process_catalog_photo(uploaded_file) -> tuple[ContentFile, ContentFile]:
    if uploaded_file is None:
        raise ValidationError("Choisissez une image.")
    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("Formats acceptés : JPEG, PNG ou WebP.")
    size = getattr(uploaded_file, "size", None)
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise ValidationError("Image trop lourde (max 5 Mo).")
    raw = uploaded_file.read()
    if not raw:
        raise ValidationError("Fichier image vide.")
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValidationError("Image trop lourde (max 5 Mo).")
    try:
        with Image.open(BytesIO(raw)) as image:
            image.load()
            full_bytes = _encode_webp(image, max_edge=FULL_MAX_EDGE, quality=82)
            thumb_bytes = _encode_webp(image, max_edge=THUMB_MAX_EDGE, quality=78)
    except UnidentifiedImageError as exc:
        raise ValidationError("Image illisible.") from exc
    except OSError as exc:
        raise ValidationError("Impossible de traiter l’image.") from exc
    return ContentFile(full_bytes, name="photo.webp"), ContentFile(thumb_bytes, name="thumb.webp")


def _encode_webp(image: Image.Image, *, max_edge: int, quality: int) -> bytes:
    working = image.copy()
    try:
        working.thumbnail((max_edge, max_edge))
        has_alpha = working.mode in {"RGBA", "LA"} or "transparency" in working.info
        normalized = working.convert("RGBA" if has_alpha else "RGB")
        try:
            output = BytesIO()
            normalized.save(output, format="WEBP", quality=quality, method=4)
            return output.getvalue()
        finally:
            normalized.close()
    finally:
        working.close()
