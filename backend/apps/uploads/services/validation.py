from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename

# Navigateurs envoient souvent application/octet-stream pour .ai / .psd / .tif / .svg.
_OCTET_STREAM_ALLOWED_EXT = frozenset({".ai", ".psd", ".tif", ".tiff", ".svg"})
_OCTET_STREAM_CANONICAL_MIME = {
    ".ai": "application/postscript",
    ".psd": "image/vnd.adobe.photoshop",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".svg": "image/svg+xml",
}


@dataclass(frozen=True)
class ValidatedUpload:
    uploaded_file: object
    original_filename: str
    mime_type: str
    size_bytes: int


class UploadValidationService:
    def clean_original_filename(self, original_filename: str) -> str:
        candidate = get_valid_filename(Path(str(original_filename or "")).name)
        if not candidate:
            return "upload"

        suffix = Path(candidate).suffix
        stem = Path(candidate).stem
        if len(candidate) <= 255:
            return candidate

        trimmed_stem = stem[: max(1, 255 - len(suffix))]
        return f"{trimmed_stem}{suffix}"

    def validate_uploaded_file(self, uploaded_file) -> ValidatedUpload:
        if uploaded_file is None:
            raise ValidationError("A file is required.")

        original_filename = self.clean_original_filename(getattr(uploaded_file, "name", ""))
        size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
        if size_bytes <= 0:
            raise ValidationError("Empty files are not allowed.")

        if size_bytes > settings.ORDER_UPLOAD_MAX_BYTES:
            raise ValidationError("File exceeds the maximum allowed size.")

        mime_type = str(getattr(uploaded_file, "content_type", "") or "").strip().lower()
        if not mime_type:
            raise ValidationError("A valid MIME type is required.")

        allowed_mime_types = {mime.lower() for mime in settings.ORDER_UPLOAD_ALLOWED_MIME_TYPES}
        ext = Path(original_filename).suffix.lower()

        if mime_type == "application/octet-stream":
            if ext not in _OCTET_STREAM_ALLOWED_EXT:
                raise ValidationError("File type is not allowed.")
            mime_type = _OCTET_STREAM_CANONICAL_MIME.get(ext, mime_type)
        elif mime_type not in allowed_mime_types:
            raise ValidationError("File type is not allowed.")

        return ValidatedUpload(
            uploaded_file=uploaded_file,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
