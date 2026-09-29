from __future__ import annotations

import re
import subprocess
import tempfile
import warnings
from io import BytesIO
from pathlib import Path

import pymupdf
from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError

from apps.uploads.services.asset_preview import AssetPreviewError, AssetPreviewRenderer

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PDF_SIGNATURE = b"%PDF-"
_POSTSCRIPT_SIGNATURE = b"%!PS-Adobe-"
_TIFF_SIGNATURES = (b"II*\x00", b"MM\x00*")
_HEADER_BYTES = 64

_MIME_TYPES_BY_EXTENSION = {
    ".png": frozenset({"image/png"}),
    ".pdf": frozenset({"application/pdf"}),
    ".ai": frozenset(
        {
            "application/pdf",
            "application/postscript",
            "application/illustrator",
            "application/vnd.adobe.illustrator",
            "application/octet-stream",
        }
    ),
    ".eps": frozenset(
        {
            "application/postscript",
            "application/eps",
            "image/eps",
            "image/x-eps",
            "application/octet-stream",
        }
    ),
    ".tif": frozenset({"image/tiff", "image/x-tiff", "application/octet-stream"}),
    ".tiff": frozenset({"image/tiff", "image/x-tiff", "application/octet-stream"}),
}

_GHOSTSCRIPT_PAGE_RE = re.compile(rb"(?m)^%%HiResBoundingBox:")


def allowed_dtf_file(name: str, mime: str) -> bool:
    """Return whether Drive metadata describes a supported original DTF file."""
    extension = Path(str(name or "").strip()).suffix.lower()
    mime_type = str(mime or "").strip().lower()
    return mime_type in _MIME_TYPES_BY_EXTENSION.get(extension, ())


def normalize_dtf_metadata(name: str, mime: str) -> tuple[str, str]:
    """Canonicalise supported Drive metadata before the content is downloaded."""
    extension = Path(str(name or "").strip()).suffix.lower()
    mime_type = str(mime or "").strip().lower()
    if not allowed_dtf_file(name, mime_type):
        raise ValidationError("Le format ou le type MIME du fichier DTF n'est pas autorisé.")
    if extension == ".png":
        canonical_mime = "image/png"
    elif extension == ".pdf" or (extension == ".ai" and mime_type == "application/pdf"):
        canonical_mime = "application/pdf"
    elif extension == ".ai" and mime_type in {
        "application/illustrator",
        "application/vnd.adobe.illustrator",
        "application/octet-stream",
    }:
        # Drive's generic AI MIME cannot distinguish PDF-compatible AI from
        # PostScript AI until the original bytes have been downloaded.
        canonical_mime = mime_type
    elif extension in {".ai", ".eps"}:
        canonical_mime = "application/postscript"
    else:
        canonical_mime = "image/tiff"
    return extension, canonical_mime


def validate_dtf_header(name: str, mime: str, header: bytes) -> tuple[str, str]:
    """Validate extension, declared MIME and magic bytes; return canonical metadata."""
    extension = Path(str(name or "").strip()).suffix.lower()
    mime_type = str(mime or "").strip().lower()
    if not allowed_dtf_file(name, mime_type):
        raise ValidationError("Le format ou le type MIME du fichier DTF n'est pas autorisé.")

    content_header = bytes(header or b"")
    if extension == ".png" and content_header.startswith(_PNG_SIGNATURE):
        canonical_mime = "image/png"
    elif extension == ".pdf" and content_header.startswith(_PDF_SIGNATURE):
        canonical_mime = "application/pdf"
    elif extension == ".ai" and content_header.startswith(_PDF_SIGNATURE):
        canonical_mime = "application/pdf"
    elif extension in {".ai", ".eps"} and content_header.startswith(_POSTSCRIPT_SIGNATURE):
        canonical_mime = "application/postscript"
    elif extension in {".tif", ".tiff"} and content_header.startswith(_TIFF_SIGNATURES):
        canonical_mime = "image/tiff"
    else:
        raise ValidationError("La signature du fichier DTF ne correspond pas à son extension.")

    # AI may legitimately use either supported container. Other declared MIME types
    # must agree with the bytes after alias/octet-stream canonicalisation.
    if extension != ".ai" and mime_type not in {
        canonical_mime,
        "application/octet-stream",
        "application/eps",
        "image/eps",
        "image/x-eps",
        "image/x-tiff",
    }:
        raise ValidationError("Le type MIME du fichier DTF ne correspond pas à son contenu.")
    if extension == ".ai" and mime_type == "application/pdf" and canonical_mime != mime_type:
        raise ValidationError("Le type MIME du fichier AI ne correspond pas à son contenu.")
    if extension == ".ai" and mime_type == "application/postscript" and canonical_mime != mime_type:
        raise ValidationError("Le type MIME du fichier AI ne correspond pas à son contenu.")
    return extension, canonical_mime


def validate_dtf_document(fileobj, name: str, mime: str) -> tuple[str, str]:
    """Strongly validate a bounded DTF document without converting the original."""
    if not hasattr(fileobj, "read") or not hasattr(fileobj, "seek"):
        raise ValidationError("Le fichier DTF ne peut pas être lu.")

    original_position = _safe_tell(fileobj)
    try:
        fileobj.seek(0)
        max_bytes = int(getattr(settings, "POD_DRIVE_HD_MAX_BYTES", 100 * 1024 * 1024))
        content = fileobj.read(max_bytes + 1)
        if not content:
            raise ValidationError("Le fichier DTF est vide.")
        if len(content) > max_bytes:
            raise ValidationError("La taille du fichier DTF dépasse la limite autorisée.")
        extension, canonical_mime = validate_dtf_header(
            name,
            mime,
            bytes(content[:_HEADER_BYTES]),
        )
        if canonical_mime == "application/pdf":
            _validate_single_page_pdf(content)
        elif canonical_mime == "application/postscript":
            _validate_postscript(content=content, extension=extension)
        elif canonical_mime == "image/tiff":
            _validate_single_frame_tiff(content)
        else:
            _validate_png(content)
        return extension, canonical_mime
    finally:
        try:
            fileobj.seek(original_position)
        except (AttributeError, OSError, ValueError):
            pass


def _validate_png(content: bytes) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != "PNG" or getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("Le fichier PNG DTF est invalide.")
                image.verify()
    except ValidationError:
        raise
    except (
        OSError,
        SyntaxError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise ValidationError("Le fichier PNG DTF est invalide ou corrompu.") from exc


def _validate_single_frame_tiff(content: bytes) -> None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != "TIFF":
                    raise ValidationError("Le fichier TIFF DTF est invalide.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValidationError("Le fichier TIFF DTF doit contenir exactement une image.")
                image.verify()
    except ValidationError:
        raise
    except (
        OSError,
        SyntaxError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombWarning,
        Image.DecompressionBombError,
    ) as exc:
        raise ValidationError("Le fichier TIFF DTF est invalide ou corrompu.") from exc


def _validate_single_page_pdf(content: bytes) -> None:
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.needs_pass or document.page_count != 1:
                raise ValidationError("Le fichier PDF DTF doit contenir exactement une page.")
            document.load_page(0)
    except ValidationError:
        raise
    except (RuntimeError, ValueError) as exc:
        raise ValidationError("Le fichier PDF DTF est invalide ou corrompu.") from exc


def _validate_postscript(*, content: bytes, extension: str) -> None:
    # A DSC %%Pages comment is only a declaration. Ghostscript must interpret
    # every showpage: rendering the first page alone would hide extra pages.
    renderer = AssetPreviewRenderer()
    with tempfile.TemporaryDirectory(prefix="prenium-dtf-pages-") as directory:
        source_path = Path(directory) / f"source{extension}"
        source_path.write_bytes(content)
        try:
            result = subprocess.run(
                [
                    "gs",
                    "-dSAFER",
                    "-dBATCH",
                    "-dNOPAUSE",
                    "-dEPSCrop",
                    "-sDEVICE=bbox",
                    str(source_path),
                ],
                check=True,
                cwd=directory,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                timeout=renderer.ghostscript_timeout_seconds,
                preexec_fn=renderer._ghostscript_limits,
            )
        except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
            raise ValidationError("Le fichier PostScript DTF est invalide ou corrompu.") from exc
    if len(_GHOSTSCRIPT_PAGE_RE.findall(result.stderr)) != 1:
        raise ValidationError("Le fichier PostScript DTF doit contenir exactement une page.")
    try:
        preview = renderer.render_content(
            content=content,
            original_filename=f"source{extension}",
            mime_type="application/postscript",
        )
        preview.image.close()
    except AssetPreviewError as exc:
        raise ValidationError("Le fichier PostScript DTF est invalide ou corrompu.") from exc


def _safe_tell(fileobj) -> int:
    try:
        return int(fileobj.tell())
    except (AttributeError, OSError, TypeError, ValueError):
        return 0
