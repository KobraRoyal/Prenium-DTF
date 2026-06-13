from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.text import get_valid_filename

logger = logging.getLogger(__name__)

# Navigateurs envoient souvent application/octet-stream pour .ai / .psd / .tif.
_OCTET_STREAM_ALLOWED_EXT = frozenset({".ai", ".psd", ".tif", ".tiff"})
_OCTET_STREAM_CANONICAL_MIME = {
    ".ai": "application/postscript",
    ".psd": "image/vnd.adobe.photoshop",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
_SIGNATURE_PEEK_BYTES = 64
_JPEG_PREFIXES = (b"\xff\xd8\xff",)
_PNG_PREFIXES = (b"\x89PNG\r\n\x1a\n",)
_PDF_PREFIXES = (b"%PDF-",)
_POSTSCRIPT_PREFIXES = (b"%!PS-Adobe-",)
_PSD_PREFIXES = (b"8BPS",)
_TIFF_PREFIXES = (b"II*\x00", b"MM\x00*")
_SVG_MIME_TYPES = frozenset({"image/svg+xml"})
_PSD_MIME_TYPES = frozenset({"image/vnd.adobe.photoshop", "application/x-photoshop"})


@dataclass(frozen=True)
class ValidatedUpload:
    uploaded_file: object
    original_filename: str
    mime_type: str
    size_bytes: int


class UploadValidationService:
    def _reject(self, reason: str, *, filename: str, mime_type: str, ext: str) -> None:
        logger.warning(
            "Upload rejected: %s",
            reason,
            extra={
                "upload_validation_reason": reason,
                "upload_original_filename": filename,
                "upload_declared_mime_type": mime_type,
                "upload_extension": ext,
            },
        )
        raise ValidationError(reason)

    def _peek_header(self, uploaded_file, size: int = _SIGNATURE_PEEK_BYTES) -> bytes:
        if not hasattr(uploaded_file, "read"):
            raise ValidationError("File content could not be validated.")

        current_pos = None
        if hasattr(uploaded_file, "tell"):
            try:
                current_pos = uploaded_file.tell()
            except (AttributeError, OSError, ValueError):
                current_pos = None

        try:
            if hasattr(uploaded_file, "seek"):
                uploaded_file.seek(0)
            header = uploaded_file.read(size)
        except (AttributeError, OSError, ValueError) as exc:
            raise ValidationError("File content could not be validated.") from exc
        finally:
            if current_pos is not None and hasattr(uploaded_file, "seek"):
                try:
                    uploaded_file.seek(current_pos)
                except (AttributeError, OSError, ValueError):
                    pass

        return bytes(header or b"")

    def _matches_any_prefix(self, header: bytes, prefixes: tuple[bytes, ...]) -> bool:
        return any(header.startswith(prefix) for prefix in prefixes)

    def _content_matches_signature(self, *, mime_type: str, ext: str, header: bytes) -> bool:
        if mime_type == "application/pdf":
            return self._matches_any_prefix(header, _PDF_PREFIXES)
        if mime_type == "image/png":
            return self._matches_any_prefix(header, _PNG_PREFIXES)
        if mime_type == "image/jpeg":
            return self._matches_any_prefix(header, _JPEG_PREFIXES)
        if mime_type == "image/tiff":
            return self._matches_any_prefix(header, _TIFF_PREFIXES)
        if mime_type == "application/postscript":
            if ext == ".ai":
                return self._matches_any_prefix(header, _POSTSCRIPT_PREFIXES + _PDF_PREFIXES)
            return self._matches_any_prefix(header, _POSTSCRIPT_PREFIXES)
        if mime_type in _PSD_MIME_TYPES:
            return self._matches_any_prefix(header, _PSD_PREFIXES)
        return False

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

        if mime_type in _SVG_MIME_TYPES or ext == ".svg":
            self._reject(
                "SVG files are not allowed.",
                filename=original_filename,
                mime_type=mime_type,
                ext=ext,
            )

        if mime_type == "application/octet-stream":
            if ext not in _OCTET_STREAM_ALLOWED_EXT:
                self._reject(
                    "File type is not allowed.",
                    filename=original_filename,
                    mime_type=mime_type,
                    ext=ext,
                )
            mime_type = _OCTET_STREAM_CANONICAL_MIME.get(ext, mime_type)
        elif mime_type not in allowed_mime_types:
            self._reject(
                "File type is not allowed.",
                filename=original_filename,
                mime_type=mime_type,
                ext=ext,
            )

        header = self._peek_header(uploaded_file)
        if not self._content_matches_signature(mime_type=mime_type, ext=ext, header=header):
            self._reject(
                "File content does not match the declared file type.",
                filename=original_filename,
                mime_type=mime_type,
                ext=ext,
            )

        return ValidatedUpload(
            uploaded_file=uploaded_file,
            original_filename=original_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
        )
