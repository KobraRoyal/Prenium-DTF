from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from apps.uploads.models import OrderUpload, OrderUploadInspection

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SOI = b"\xff\xd8"
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}
JPEG_NO_PAYLOAD_MARKERS = {0x01, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9}


@dataclass(frozen=True)
class ExtractedUploadMetadata:
    status: str
    summary_message: str
    file_kind: str
    file_extension: str
    metadata: dict[str, object]
    image_width: int | None = None
    image_height: int | None = None


class UploadMetadataExtractionService:
    def extract(self, order_upload: OrderUpload) -> ExtractedUploadMetadata:
        file_extension = self._extract_extension(order_upload.original_filename)
        file_kind = self._detect_file_kind(order_upload.mime_type)
        metadata: dict[str, object] = {
            "mime_type": order_upload.mime_type,
            "size_bytes": order_upload.size_bytes,
            "file_extension": file_extension,
        }

        if file_kind == "pdf":
            return ExtractedUploadMetadata(
                status=OrderUploadInspection.Status.OK,
                summary_message="Basic file metadata extracted.",
                file_kind=file_kind,
                file_extension=file_extension,
                metadata=metadata,
            )

        if file_kind == "unknown":
            return ExtractedUploadMetadata(
                status=OrderUploadInspection.Status.WARNING,
                summary_message=(
                    "No specialized metadata extractor is available for this file type."
                ),
                file_kind=file_kind,
                file_extension=file_extension,
                metadata=metadata,
            )

        try:
            image_width, image_height = self._extract_image_dimensions(order_upload)
        except ValueError:
            metadata["image_readable"] = False
            return ExtractedUploadMetadata(
                status=OrderUploadInspection.Status.ERROR,
                summary_message="Image metadata could not be read.",
                file_kind=file_kind,
                file_extension=file_extension,
                metadata=metadata,
            )

        metadata["image_readable"] = True
        metadata["image_width"] = image_width
        metadata["image_height"] = image_height
        return ExtractedUploadMetadata(
            status=OrderUploadInspection.Status.OK,
            summary_message="Basic image metadata extracted.",
            file_kind=file_kind,
            file_extension=file_extension,
            metadata=metadata,
            image_width=image_width,
            image_height=image_height,
        )

    def _extract_extension(self, filename: str) -> str:
        _root, extension = os.path.splitext(filename or "")
        return extension.lower().lstrip(".")

    def _detect_file_kind(self, mime_type: str) -> str:
        if mime_type in {"image/png", "image/jpeg"}:
            return "image"
        if mime_type == "application/pdf":
            return "pdf"
        return "unknown"

    def _extract_image_dimensions(self, order_upload: OrderUpload) -> tuple[int, int]:
        order_upload.file.open("rb")
        try:
            header = order_upload.file.read(32)
            order_upload.file.seek(0)

            if order_upload.mime_type == "image/png":
                return self._parse_png_dimensions(header)

            if order_upload.mime_type == "image/jpeg":
                return self._parse_jpeg_dimensions(order_upload.file)
        finally:
            order_upload.file.close()

        raise ValueError("Unsupported image format.")

    def _parse_png_dimensions(self, header: bytes) -> tuple[int, int]:
        if len(header) < 24 or not header.startswith(PNG_SIGNATURE):
            raise ValueError("Unreadable PNG header.")

        chunk_type = header[12:16]
        if chunk_type != b"IHDR":
            raise ValueError("PNG header missing IHDR.")

        width = struct.unpack(">I", header[16:20])[0]
        height = struct.unpack(">I", header[20:24])[0]
        if width <= 0 or height <= 0:
            raise ValueError("PNG dimensions are invalid.")
        return width, height

    def _parse_jpeg_dimensions(self, file_obj) -> tuple[int, int]:
        if file_obj.read(2) != JPEG_SOI:
            raise ValueError("Unreadable JPEG header.")

        while True:
            marker_prefix = file_obj.read(1)
            if marker_prefix != b"\xff":
                raise ValueError("Invalid JPEG marker prefix.")

            marker_code = file_obj.read(1)
            while marker_code == b"\xff":
                marker_code = file_obj.read(1)

            if not marker_code:
                raise ValueError("Unexpected end of JPEG stream.")

            marker = marker_code[0]
            if marker in JPEG_NO_PAYLOAD_MARKERS:
                if marker == 0xD9:
                    break
                continue

            segment_length_bytes = file_obj.read(2)
            if len(segment_length_bytes) != 2:
                raise ValueError("Invalid JPEG segment length.")
            segment_length = struct.unpack(">H", segment_length_bytes)[0]
            if segment_length < 2:
                raise ValueError("Invalid JPEG segment size.")

            if marker in JPEG_SOF_MARKERS:
                payload = file_obj.read(segment_length - 2)
                if len(payload) < 5:
                    raise ValueError("JPEG SOF payload is incomplete.")
                height = struct.unpack(">H", payload[1:3])[0]
                width = struct.unpack(">H", payload[3:5])[0]
                if width <= 0 or height <= 0:
                    raise ValueError("JPEG dimensions are invalid.")
                return width, height

            skipped = file_obj.seek(segment_length - 2, os.SEEK_CUR)
            if skipped is None:
                continue

        raise ValueError("JPEG dimensions not found.")
