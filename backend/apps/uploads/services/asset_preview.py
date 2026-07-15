from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import pymupdf
from PIL import Image, UnidentifiedImageError
from psd_tools import PSDImage

from apps.uploads.services.asset_dpi import (
    extract_pdf_source_metrics,
    extract_pillow_source_metrics,
    extract_psd_source_metrics,
    parse_eps_page_size_inches,
    pdf_page_has_vector_artwork,
)


class AssetPreviewError(ValueError):
    pass


@dataclass
class RenderedAssetPreview:
    image: Image.Image
    format_name: str
    source_width: int
    source_height: int
    dpi_x: float | None = None
    dpi_y: float | None = None
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


class AssetPreviewRenderer:
    max_render_side = 2400
    vector_dpi = 144
    ghostscript_timeout_seconds = 20

    def render(self, *, version) -> RenderedAssetPreview:
        content = self._read_content(version)
        extension = Path(version.original_filename).suffix.lower()
        if version.mime_type == "application/pdf" or content.startswith(b"%PDF-"):
            return self._render_pdf(content=content, extension=extension)
        if extension == ".psd" or version.mime_type in {
            "image/vnd.adobe.photoshop",
            "application/x-photoshop",
        }:
            return self._render_psd(content=content)
        if extension in {".ai", ".eps"} or version.mime_type == "application/postscript":
            return self._render_postscript(content=content, extension=extension)
        return self._render_pillow(content=content, extension=extension)

    def _read_content(self, version) -> bytes:
        version.file.open("rb")
        try:
            content = version.file.read()
        finally:
            version.file.close()
        if not content:
            raise AssetPreviewError("Le fichier est vide ou illisible.")
        return content

    def _render_pillow(self, *, content: bytes, extension: str) -> RenderedAssetPreview:
        try:
            with Image.open(BytesIO(content)) as source:
                source.seek(0)
                source.load()
                image = source.copy()
                metrics = extract_pillow_source_metrics(source)
                dpi_x, dpi_y = metrics.dpi_x, metrics.dpi_y
                warnings = []
                if extension in {".tif", ".tiff"} and getattr(source, "n_frames", 1) > 1:
                    warnings.append("Aperçu généré depuis la première page du TIFF.")
                if dpi_x is None or dpi_y is None:
                    warnings.append("DPI source absent dans les métadonnées du fichier.")
                width, height = image.size
                return RenderedAssetPreview(
                    image=image,
                    format_name=str(source.format or extension.lstrip(".")).upper(),
                    source_width=width,
                    source_height=height,
                    dpi_x=dpi_x,
                    dpi_y=dpi_y,
                    warnings=warnings,
                    metadata={
                        "frames": getattr(source, "n_frames", 1),
                        "dimension_basis": metrics.dimension_basis,
                        "dpi_source": metrics.dpi_source,
                        "embedded_display_width_in": metrics.display_width_in,
                        "embedded_display_height_in": metrics.display_height_in,
                    },
                )
        except (OSError, UnidentifiedImageError) as error:
            raise AssetPreviewError("Aucun aperçu ne peut être généré pour ce fichier.") from error

    def _render_psd(self, *, content: bytes) -> RenderedAssetPreview:
        try:
            document = PSDImage.open(BytesIO(content))
            metrics = extract_psd_source_metrics(document)
            image = document.composite()
            if image is None:
                raise AssetPreviewError("Le PSD ne contient pas d’aperçu composite exploitable.")
            image.load()
            warnings = ["Aperçu composite du PSD ; les calques originaux restent inchangés."]
            if metrics.dpi_x is None or metrics.dpi_y is None:
                warnings.append("DPI source absent dans le PSD.")
            return RenderedAssetPreview(
                image=image.copy(),
                format_name="PSD",
                source_width=int(metrics.width_px or document.width),
                source_height=int(metrics.height_px or document.height),
                dpi_x=metrics.dpi_x,
                dpi_y=metrics.dpi_y,
                warnings=warnings,
                metadata={
                    "layers": len(document),
                    "color_mode": str(document.color_mode.name),
                    "dimension_basis": metrics.dimension_basis,
                    "dpi_source": metrics.dpi_source,
                    "embedded_display_width_in": metrics.display_width_in,
                    "embedded_display_height_in": metrics.display_height_in,
                },
            )
        except AssetPreviewError:
            raise
        except (ImportError, OSError, ValueError) as error:
            try:
                fallback = self._render_pillow(content=content, extension=".psd")
            except AssetPreviewError:
                raise AssetPreviewError("Le PSD ne peut pas être prévisualisé.") from error
            fallback.format_name = "PSD"
            fallback.warnings.append("Aperçu fusionné du PSD ; les calques restent inchangés.")
            return fallback

    def _render_pdf(self, *, content: bytes, extension: str) -> RenderedAssetPreview:
        try:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                if document.page_count < 1:
                    raise AssetPreviewError("Le document ne contient aucune page.")
                page = document.load_page(0)
                source_metrics = extract_pdf_source_metrics(document, page)
                longest_side_points = max(float(page.rect.width), float(page.rect.height), 1.0)
                zoom = min(2.0, self.max_render_side / longest_side_points)
                render_dpi = round(72 * zoom, 2)
                pixmap = page.get_pixmap(
                    matrix=pymupdf.Matrix(zoom, zoom),
                    colorspace=pymupdf.csRGB,
                    alpha=True,
                    annots=False,
                )
                image = Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)
                label = "AI compatible PDF" if extension == ".ai" else "PDF"
                has_vector_artwork = pdf_page_has_vector_artwork(page)
                has_raster_artwork = bool(page.get_image_info(xrefs=True))
                warnings = [f"Aperçu généré depuis la première page du {label}."]
                if source_metrics.dpi_x is None or source_metrics.dpi_y is None:
                    warnings.append(
                        "Document vectoriel ou sans image embarquée : "
                        "la résolution source n’est pas applicable."
                    )
                return RenderedAssetPreview(
                    image=image,
                    format_name=label,
                    source_width=int(source_metrics.width_px or 1),
                    source_height=int(source_metrics.height_px or 1),
                    dpi_x=source_metrics.dpi_x,
                    dpi_y=source_metrics.dpi_y,
                    warnings=warnings,
                    metadata={
                        "pages": document.page_count,
                        "page_width_points": round(float(page.rect.width), 2),
                        "page_height_points": round(float(page.rect.height), 2),
                        "page_width_in": source_metrics.page_width_in,
                        "page_height_in": source_metrics.page_height_in,
                        "embedded_display_width_in": source_metrics.display_width_in,
                        "embedded_display_height_in": source_metrics.display_height_in,
                        "placement_width_in": source_metrics.placement_width_in,
                        "placement_height_in": source_metrics.placement_height_in,
                        "placement_effective_dpi": source_metrics.placement_effective_dpi,
                        "artboard_width_mm": source_metrics.artboard_width_mm,
                        "artboard_height_mm": source_metrics.artboard_height_mm,
                        "uses_artboard_dimensions": source_metrics.uses_artboard_dimensions,
                        "has_vector_artwork": has_vector_artwork,
                        "has_raster_artwork": has_raster_artwork,
                        "is_pure_vector": has_vector_artwork and not has_raster_artwork,
                        "dpi_source": source_metrics.dpi_source,
                        "render_dpi": render_dpi,
                        "dimension_basis": source_metrics.dimension_basis,
                    },
                )
        except AssetPreviewError:
            raise
        except (RuntimeError, ValueError) as error:
            raise AssetPreviewError(
                "Le PDF ou AI compatible PDF ne peut pas être prévisualisé."
            ) from error

    def _render_postscript(self, *, content: bytes, extension: str) -> RenderedAssetPreview:
        page_size = parse_eps_page_size_inches(content)
        has_raster_artwork = self._postscript_has_raster_artwork(content)
        with tempfile.TemporaryDirectory(prefix="prenium-preview-") as directory:
            directory_path = Path(directory)
            source_path = directory_path / f"source{extension or '.eps'}"
            output_path = directory_path / "preview.png"
            source_path.write_bytes(content)
            command = [
                "gs",
                "-dSAFER",
                "-dBATCH",
                "-dNOPAUSE",
                "-dFirstPage=1",
                "-dLastPage=1",
                "-dEPSCrop",
                "-dTextAlphaBits=4",
                "-dGraphicsAlphaBits=4",
                "-sDEVICE=pngalpha",
                f"-r{self.vector_dpi}",
                f"-sOutputFile={output_path}",
                str(source_path),
            ]
            try:
                subprocess.run(
                    command,
                    check=True,
                    cwd=directory,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=self.ghostscript_timeout_seconds,
                    preexec_fn=self._ghostscript_limits,
                )
                with Image.open(output_path) as source:
                    source.load()
                    image = source.copy()
            except (FileNotFoundError, OSError, subprocess.SubprocessError) as error:
                raise AssetPreviewError(
                    "Le fichier EPS ou AI ne peut pas être prévisualisé."
                ) from error

        if page_size is not None:
            page_width_in, page_height_in = page_size
            source_width = max(int(round(page_width_in * 72)), 1)
            source_height = max(int(round(page_height_in * 72)), 1)
        else:
            page_width_in = page_height_in = None
            source_width, source_height = image.size

        return RenderedAssetPreview(
            image=image,
            format_name="AI" if extension == ".ai" else "EPS",
            source_width=source_width,
            source_height=source_height,
            dpi_x=None,
            dpi_y=None,
            warnings=[
                "Aperçu rasterisé ; le fichier vectoriel original reste inchangé.",
                "Document vectoriel : la résolution source n’est pas applicable.",
            ],
            metadata={
                "renderer": "ghostscript",
                "render_dpi": self.vector_dpi,
                "has_vector_artwork": True,
                "has_raster_artwork": has_raster_artwork,
                "is_pure_vector": not has_raster_artwork,
                "page_width_in": page_width_in,
                "page_height_in": page_height_in,
                "dimension_basis": "page" if page_size is not None else "preview",
            },
        )

    @staticmethod
    def _postscript_has_raster_artwork(content: bytes) -> bool:
        sample = content.lower()
        raster_markers = (
            b"/imagetype",
            b" colorimage",
            b" imagemask",
            b"%ai5_beginraster",
            b"%ai7_beginraster",
        )
        return any(marker in sample for marker in raster_markers)

    @staticmethod
    def _ghostscript_limits() -> None:
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (20, 20))
            resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_FSIZE, (50 * 1024 * 1024, 50 * 1024 * 1024))
        except (ImportError, OSError, ValueError):
            return
