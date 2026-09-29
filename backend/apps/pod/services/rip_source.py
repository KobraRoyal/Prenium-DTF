from __future__ import annotations

import hashlib
import os
import uuid
import warnings
from dataclasses import dataclass
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import transaction
from PIL import Image

from apps.pod.models import PodDriveHdSource
from apps.pod.services.hd_formats import (
    allowed_dtf_file,
    validate_dtf_document,
    validate_dtf_header,
)
from apps.uploads.models import AssetVersion

_CHUNK_SIZE = 1024 * 1024
_FORMAT_RULES = {
    ".png": ({".png"}, {"image/png"}),
}


@dataclass(frozen=True)
class StagedRipSource:
    path: Path
    size_bytes: int
    checksum_sha256: str


class RipSourceService:
    """Validate an exact customer-owned asset version before a RIP export."""

    def resolve(self, *, slot, store, technique) -> AssetVersion:
        version = getattr(slot, "source_asset_version", None)
        if version is None:
            raise ValidationError(
                "Le slot ne possède aucun fichier HD AssetVersion. "
                "Une ancienne référence texte seule n'est pas imprimable."
            )
        self.validate_version(
            version=version,
            store=store,
            technique=technique,
            drive_source=getattr(slot, "source_drive_hd", None),
        )
        return version

    def validate_version(
        self, *, version: AssetVersion, store, technique, drive_source=None
    ) -> None:
        customer_id = getattr(store, "customer_id", None)
        if customer_id is None:
            raise ValidationError(
                "La boutique doit être liée à un Customer avant toute production POD."
            )
        if version.customer_id != customer_id or version.asset.customer_id != customer_id:
            raise ValidationError("Le fichier HD n'appartient pas au client de la boutique.")
        if version.asset.is_archived:
            raise ValidationError("Le fichier HD source est archivé.")
        if version.analysis_status != AssetVersion.AnalysisStatus.READY:
            raise ValidationError("Le fichier HD doit avoir une analyse READY avant impression.")
        if not version.file or not version.file.name:
            raise ValidationError("Le fichier HD source est absent du stockage.")
        self._validate_declared_format(version=version, technique=technique)
        if technique.code == "dtf" and Path(version.original_filename).suffix.lower() in {
            ".pdf",
            ".ai",
            ".eps",
        }:
            if (
                drive_source is None
                or drive_source.status != PodDriveHdSource.Status.READY
                or drive_source.customer_id != customer_id
                or drive_source.asset_version_id != version.pk
            ):
                raise ValidationError(
                    "Les fichiers DTF vectoriels doivent provenir de la bibliothèque Drive "
                    "HD validée par l'atelier."
                )

    def stage(
        self, *, version: AssetVersion, store, technique, destination: Path, drive_source=None
    ) -> StagedRipSource:
        if not transaction.get_connection().in_atomic_block:
            raise ValidationError("Export RIP hors transaction interdit.")
        version = (
            AssetVersion.objects.select_for_update().select_related("asset").get(pk=version.pk)
        )
        if drive_source is not None:
            drive_source = (
                PodDriveHdSource.objects.select_for_update().filter(pk=drive_source.pk).first()
            )
        self.validate_version(
            version=version,
            store=store,
            technique=technique,
            drive_source=drive_source,
        )
        extension = self.source_extension(version=version, technique=technique)
        if destination.suffix.lower() != extension:
            raise ValidationError("L'extension du fichier RIP ne correspond pas à la source HD.")
        staging = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.part")
        hasher = hashlib.sha256()
        size_bytes = 0
        header = bytearray()
        try:
            try:
                source = version.file.open("rb")
            except (FileNotFoundError, OSError, ValueError) as exc:
                raise ValidationError(
                    "Le fichier HD source est introuvable dans le stockage."
                ) from exc
            try:
                with source, staging.open("xb") as target:
                    while True:
                        chunk = source.read(_CHUNK_SIZE)
                        if not chunk:
                            break
                        if len(header) < 1024:
                            header.extend(chunk[: 1024 - len(header)])
                        hasher.update(chunk)
                        size_bytes += len(chunk)
                        target.write(chunk)
                    target.flush()
                    os.fsync(target.fileno())
            except OSError as exc:
                raise ValidationError(
                    "Impossible de lire ou de copier le fichier HD source."
                ) from exc

            checksum = hasher.hexdigest()
            if size_bytes < 1:
                raise ValidationError("Le fichier HD source est vide.")
            if size_bytes != int(version.size_bytes or 0):
                raise ValidationError("Le fichier HD source est corrompu (taille incohérente).")
            if checksum.lower() != (version.sha256 or "").strip().lower():
                raise ValidationError("Le fichier HD source est corrompu (SHA-256 incohérent).")
            if technique.code == "dtf":
                validate_dtf_header(version.original_filename, version.mime_type, bytes(header))
                with staging.open("rb") as staged_file:
                    validate_dtf_document(
                        staged_file,
                        version.original_filename,
                        version.mime_type,
                    )
            else:
                if not self._signature_matches(extension=extension, header=bytes(header)):
                    raise ValidationError(
                        f"La signature du fichier HD ne correspond pas au format {extension}."
                    )
                self._validate_png(staging)
            return StagedRipSource(
                path=staging,
                size_bytes=size_bytes,
                checksum_sha256=checksum,
            )
        except Exception:
            staging.unlink(missing_ok=True)
            raise

    @staticmethod
    def publish(*, staged: StagedRipSource, destination: Path) -> None:
        if destination.exists():
            raise ValidationError(f"Collision de nom RIP : {destination.name}.")
        os.replace(staged.path, destination)

    def _validate_declared_format(self, *, version: AssetVersion, technique) -> None:
        extension = self._normalized_extension(technique.export_extension)
        if technique.code == "dtf":
            if not allowed_dtf_file(version.original_filename, version.mime_type):
                raise ValidationError(
                    "Le fichier HD DTF doit être un PNG, PDF, AI, EPS ou TIFF compatible."
                )
            return
        allowed_extensions, allowed_mimes = _FORMAT_RULES[extension]
        source_extension = Path(version.original_filename or "").suffix.lower()
        if source_extension not in allowed_extensions:
            raise ValidationError(
                f"Le fichier HD doit utiliser une extension compatible avec {extension}."
            )
        mime_type = (version.mime_type or "").partition(";")[0].strip().lower()
        if mime_type not in allowed_mimes:
            raise ValidationError(
                f"Le type MIME {mime_type or 'inconnu'} est incompatible avec {extension}."
            )

    def source_extension(self, *, version: AssetVersion, technique) -> str:
        self._validate_declared_format(version=version, technique=technique)
        if technique.code == "dtf":
            return Path(version.original_filename).suffix.lower()
        return self._normalized_extension(technique.export_extension)

    @staticmethod
    def _normalized_extension(value: str) -> str:
        extension = (value or "").strip().lower()
        if extension and not extension.startswith("."):
            extension = f".{extension}"
        if extension not in _FORMAT_RULES:
            raise ValidationError(
                f"Format RIP non validé pour l'export automatique : {extension or 'vide'}. "
                "Seul le PNG analysé est autorisé."
            )
        return extension

    @staticmethod
    def _validate_png(path: Path) -> None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    if image.format != "PNG":
                        raise ValidationError("Le fichier HD n'est pas un PNG valide.")
                    image.verify()
        except (
            OSError,
            SyntaxError,
            ValueError,
            Image.DecompressionBombWarning,
            Image.DecompressionBombError,
        ) as exc:
            raise ValidationError("Le fichier HD PNG est invalide ou corrompu.") from exc

    @staticmethod
    def _signature_matches(*, extension: str, header: bytes) -> bool:
        if extension == ".png":
            return header.startswith(b"\x89PNG\r\n\x1a\n")
        return False
