from __future__ import annotations

import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image

from apps.gang_sheets.services.cropping import CropBox, crop_image
from apps.uploads.services.asset_preview import AssetPreviewRenderer

MM_TO_POINTS = 72 / 25.4
DIRECT_RASTER_MIME_TYPES = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/tiff",
    }
)
POSTSCRIPT_EXTENSIONS = frozenset({".ai", ".eps"})


class HybridPdfCompositionError(RuntimeError):
    pass


class GangSheetHybridPdfComposer:
    """Compose un PDF de production sans aplatir les sources vectorielles ou mixtes."""

    def __init__(self, *, preview_renderer=None):
        self.preview_renderer = preview_renderer or AssetPreviewRenderer()

    def compose(self, *, sheet, items) -> bytes:
        output = pymupdf.open()
        source_documents: dict[int, pymupdf.Document] = {}
        source_contents: dict[int, bytes] = {}
        raster_streams: dict[int, bytes] = {}
        raster_xrefs: dict[int, int] = {}
        crops = {
            entry.asset_id: CropBox.from_source_asset(entry)
            for entry in sheet.source_assets.filter(customer=sheet.customer)
        }
        try:
            page = output.new_page(
                width=float(sheet.width_mm) * MM_TO_POINTS,
                height=float(sheet.height_mm) * MM_TO_POINTS,
            )
            for item in items:
                version = item.asset_version
                crop = crops.get(version.asset_id, CropBox.full())
                content = source_contents.get(version.pk)
                if content is None:
                    content = self._read_version(version)
                    source_contents[version.pk] = content
                if self._is_pdf_source(version=version, content=content):
                    source_document = source_documents.get(version.pk)
                    if source_document is None:
                        source_document = self._open_pdf(content)
                        source_documents[version.pk] = source_document
                    self._place_pdf(
                        page=page,
                        item=item,
                        source_document=source_document,
                        crop=crop,
                    )
                elif self._is_postscript_source(version=version):
                    source_document = source_documents.get(version.pk)
                    if source_document is None:
                        source_document = self._open_pdf(
                            self._convert_postscript_to_pdf(version=version, content=content)
                        )
                        source_documents[version.pk] = source_document
                    self._place_pdf(
                        page=page,
                        item=item,
                        source_document=source_document,
                        crop=crop,
                    )
                else:
                    stream = raster_streams.get(version.pk)
                    if stream is None:
                        stream = self._raster_stream(
                            version=version,
                            content=content,
                            crop=crop,
                        )
                        raster_streams[version.pk] = stream
                    raster_xrefs[version.pk] = self._place_raster(
                        page=page,
                        item=item,
                        stream=stream,
                        existing_xref=raster_xrefs.get(version.pk),
                    )

            output.set_metadata(
                {
                    "title": sheet.name,
                    "author": "Prenium DTF — Gang Sheet Generator Pro",
                    "subject": (
                        f"Planche hybride de production {sheet.width_mm} × {sheet.height_mm} mm"
                    ),
                    "keywords": "Prenium DTF, gang sheet, hybrid PDF, source preserving",
                    "creator": "Prenium DTF",
                    "producer": "PyMuPDF",
                }
            )
            return output.tobytes(
                garbage=4,
                deflate=True,
                deflate_images=False,
                deflate_fonts=True,
            )
        except (RuntimeError, ValueError, OSError) as error:
            if isinstance(error, HybridPdfCompositionError):
                raise
            raise HybridPdfCompositionError(
                "Le PDF hybride de production ne peut pas être généré."
            ) from error
        finally:
            for document in source_documents.values():
                document.close()
            output.close()

    def _place_pdf(self, *, page, item, source_document, crop: CropBox) -> None:
        if source_document.page_count < 1:
            raise HybridPdfCompositionError("Le document source ne contient aucune page.")
        source_page = source_document.load_page(0)
        source_rect = source_page.rect
        clip = pymupdf.Rect(
            source_rect.x0 + float(crop.x) * source_rect.width,
            source_rect.y0 + float(crop.y) * source_rect.height,
            source_rect.x0 + float(crop.x + crop.width) * source_rect.width,
            source_rect.y0 + float(crop.y + crop.height) * source_rect.height,
        )
        page.show_pdf_page(
            self._item_rect(item),
            source_document,
            0,
            keep_proportion=False,
            overlay=True,
            rotate=int(item.rotation) % 360,
            clip=clip,
        )

    def _place_raster(self, *, page, item, stream: bytes, existing_xref: int | None) -> int:
        kwargs = {"xref": existing_xref} if existing_xref else {"stream": stream}
        return page.insert_image(
            self._item_rect(item),
            keep_proportion=False,
            overlay=True,
            rotate=int(item.rotation) % 360,
            **kwargs,
        )

    def _raster_stream(self, *, version, content: bytes, crop: CropBox) -> bytes:
        if version.mime_type in DIRECT_RASTER_MIME_TYPES and crop.is_full:
            return content
        if version.mime_type in DIRECT_RASTER_MIME_TYPES:
            try:
                with Image.open(BytesIO(content)) as source:
                    source.seek(0)
                    source.load()
                    image = source.copy()
                    image.info.update(source.info)
            except (OSError, ValueError) as error:
                raise HybridPdfCompositionError(
                    "Le visuel raster ne peut pas être recadré."
                ) from error
        else:
            rendered = self.preview_renderer.render(version=version)
            image = rendered.image
        try:
            cropped = crop_image(image, crop)
            image.close()
            image = cropped
            if image.mode not in {"RGB", "RGBA"}:
                converted = image.convert("RGBA")
                image.close()
                image = converted
            output = BytesIO()
            save_options = {}
            icc_profile = image.info.get("icc_profile")
            if icc_profile:
                save_options["icc_profile"] = icc_profile
            image.save(output, format="PNG", **save_options)
            return output.getvalue()
        finally:
            image.close()

    def _convert_postscript_to_pdf(self, *, version, content: bytes) -> bytes:
        extension = Path(version.original_filename).suffix.lower()
        suffix = extension if extension in POSTSCRIPT_EXTENSIONS else ".eps"
        with tempfile.TemporaryDirectory(prefix="prenium-gang-vector-") as directory:
            source_path = Path(directory) / f"source{suffix}"
            output_path = Path(directory) / "source.pdf"
            source_path.write_bytes(content)
            command = [
                "gs",
                "-dSAFER",
                "-dBATCH",
                "-dNOPAUSE",
                "-dEPSCrop",
                "-dAutoRotatePages=/None",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.7",
                f"-sOutputFile={output_path}",
                str(source_path),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    cwd=directory,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=self.preview_renderer.ghostscript_timeout_seconds,
                )
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                raise HybridPdfCompositionError(
                    "Le fichier EPS/AI ne peut pas être converti en PDF vectoriel."
                ) from error
            if not output_path.exists() or output_path.stat().st_size == 0:
                raise HybridPdfCompositionError("La conversion vectorielle EPS/AI est vide.")
            return output_path.read_bytes()

    @staticmethod
    def _item_rect(item) -> pymupdf.Rect:
        x = float(item.x_mm) * MM_TO_POINTS
        y = float(item.y_mm) * MM_TO_POINTS
        width = float(item.effective_width_mm) * MM_TO_POINTS
        height = float(item.effective_height_mm) * MM_TO_POINTS
        return pymupdf.Rect(x, y, x + width, y + height)

    @staticmethod
    def _is_pdf_source(*, version, content: bytes) -> bool:
        return version.mime_type == "application/pdf" or content.lstrip().startswith(b"%PDF-")

    @staticmethod
    def _is_postscript_source(*, version) -> bool:
        extension = Path(version.original_filename).suffix.lower()
        return version.mime_type == "application/postscript" or extension in POSTSCRIPT_EXTENSIONS

    @staticmethod
    def _open_pdf(content: bytes) -> pymupdf.Document:
        try:
            document = pymupdf.open(stream=content, filetype="pdf")
        except (RuntimeError, ValueError) as error:
            raise HybridPdfCompositionError("Le document PDF source est illisible.") from error
        if document.needs_pass:
            document.close()
            raise HybridPdfCompositionError("Les PDF protégés par mot de passe ne sont pas admis.")
        return document

    @staticmethod
    def _read_version(version) -> bytes:
        version.file.open("rb")
        try:
            content = version.file.read()
        finally:
            version.file.close()
        if not content:
            raise HybridPdfCompositionError("Le fichier source est vide.")
        return content
