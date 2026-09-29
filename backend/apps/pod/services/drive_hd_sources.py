from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.utils import timezone
from django.utils.text import get_valid_filename

from apps.auditlog.services import record_event
from apps.pod.models import PodDriveHdSource, PodRecipeSlot
from apps.pod.services.hd_formats import (
    allowed_dtf_file,
    normalize_dtf_metadata,
    validate_dtf_document,
)
from apps.pod.services.validation import require_staff_perm
from apps.uploads.models import Asset, AssetVersion
from apps.uploads.services.drive import (
    GoogleDriveConfigurationError,
    GoogleDriveGateway,
    GoogleDriveSyncError,
)

_DRIVE_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,255}$")
_MD5_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_CHUNK_SIZE = 1024 * 1024
_MAX_LIBRARY_PAGES = 10
_IMPORT_LEASE = timedelta(minutes=15)


@dataclass(frozen=True)
class DriveHdOption:
    file_id: str
    name: str


@dataclass(frozen=True)
class DriveHdOptionsResult:
    options: tuple[DriveHdOption, ...]
    configured: bool
    error: str = ""
    empty_file_count: int = 0


class DriveHdSourceService:
    manage_permission = "pod.manage_pod_catalog"

    def __init__(self, *, gateway_factory=GoogleDriveGateway):
        self.gateway_factory = gateway_factory

    def list_options(self, *, actor, refresh: bool = False) -> DriveHdOptionsResult:
        folder_id = self._source_folder_id()
        if not folder_id:
            return DriveHdOptionsResult(
                options=(),
                configured=False,
                error="Le dossier Drive des fichiers HD n'est pas configuré.",
            )
        if actor is None or not actor.has_perm(self.manage_permission):
            return DriveHdOptionsResult(options=(), configured=True)
        require_staff_perm(
            actor,
            self.manage_permission,
            source="pod.drive_hd_library",
            action="pod.drive_hd_source.permission_rejected",
        )
        try:
            gateway = self.gateway_factory()
            cache_key = self._options_cache_key(gateway=gateway, folder_id=folder_id)
            cached_options = None if refresh else cache.get(cache_key)
            if isinstance(cached_options, dict):
                return DriveHdOptionsResult(
                    options=tuple(
                        DriveHdOption(*item) for item in cached_options.get("options", ())
                    ),
                    configured=True,
                    empty_file_count=int(cached_options.get("empty_file_count", 0)),
                )
            self._validate_source_folder(gateway=gateway, folder_id=folder_id)
            files = []
            page_token = None
            seen_tokens = set()
            for _page_number in range(_MAX_LIBRARY_PAGES):
                page, next_page_token = gateway.list_binary_files(
                    parent_id=folder_id,
                    page_token=page_token,
                    page_size=100,
                )
                files.extend(page)
                if not next_page_token:
                    break
                if next_page_token in seen_tokens:
                    raise GoogleDriveSyncError("Drive pagination token repeated.")
                seen_tokens.add(next_page_token)
                page_token = next_page_token
            else:
                raise GoogleDriveSyncError(
                    "Drive HD library exceeds the supported 1000-file drawer limit."
                )
        except (
            GoogleDriveConfigurationError,
            GoogleDriveSyncError,
            ValidationError,
            ValueError,
            OSError,
        ):
            return DriveHdOptionsResult(
                options=(),
                configured=True,
                error="La bibliothèque Drive HD est temporairement indisponible.",
            )
        options = tuple(
            DriveHdOption(file_id=item.file_id, name=item.name)
            for item in files
            if self._is_list_candidate(item=item, folder_id=folder_id, gateway=gateway)
        )
        empty_file_count = sum(
            item.size == 0 and allowed_dtf_file(item.name, item.mime_type)
            for item in files
        )
        cache.set(
            cache_key,
            {
                "options": tuple((item.file_id, item.name) for item in options),
                "empty_file_count": empty_file_count,
            },
            timeout=30,
        )
        return DriveHdOptionsResult(
            options=options,
            configured=True,
            empty_file_count=empty_file_count,
        )

    def select(
        self,
        *,
        customer,
        drive_file_id: str,
        actor,
        source: str,
    ) -> PodDriveHdSource:
        normalized_file_id = str(drive_file_id or "").strip()
        if customer is None:
            raise ValidationError(
                "La boutique doit être liée à un Customer avant de sélectionner un fichier HD."
            )
        require_staff_perm(
            actor,
            self.manage_permission,
            source=source,
            action="pod.drive_hd_source.permission_rejected",
        )
        if not _DRIVE_FILE_ID_RE.fullmatch(normalized_file_id):
            self._audit_rejection(
                actor=actor,
                customer=customer,
                source=source,
                reason="invalid_file_id",
            )
            raise ValidationError("Identifiant du fichier Drive HD invalide.")
        try:
            gateway = self.gateway_factory()
            self._validate_source_folder(
                gateway=gateway,
                folder_id=self._source_folder_id(),
            )
            metadata = gateway.get_file_metadata(normalized_file_id)
            validated = self._validate_metadata(
                metadata=metadata,
                expected_file_id=normalized_file_id,
                gateway=gateway,
            )
        except (
            GoogleDriveConfigurationError,
            GoogleDriveSyncError,
            ValidationError,
            OSError,
        ) as exc:
            self._audit_rejection(
                actor=actor,
                customer=customer,
                source=source,
                reason=type(exc).__name__,
            )
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError("Impossible de valider le fichier Drive HD.") from exc

        drive_source, created = PodDriveHdSource.objects.get_or_create(
            customer=customer,
            drive_file_id=validated["file_id"],
            drive_version=validated["drive_version"],
            defaults={
                "selected_by": actor,
                "canonical_url": self._canonical_url(validated["file_id"]),
                "original_filename": validated["name"],
                "mime_type": validated["mime_type"],
                "size_bytes": validated["size_bytes"],
                "md5_checksum": validated["md5_checksum"],
            },
        )
        if not created:
            immutable_metadata = (
                drive_source.original_filename == validated["name"]
                and drive_source.mime_type == validated["mime_type"]
                and drive_source.size_bytes == validated["size_bytes"]
                and drive_source.md5_checksum.lower() == validated["md5_checksum"].lower()
            )
            if not immutable_metadata:
                self._audit_rejection(
                    actor=actor,
                    customer=customer,
                    source=source,
                    reason="version_metadata_changed",
                )
                raise ValidationError("Les métadonnées de cette version Drive ont changé.")
            if drive_source.status == PodDriveHdSource.Status.FAILED:
                drive_source.status = PodDriveHdSource.Status.PENDING
                drive_source.last_error = ""
                drive_source.selected_by = actor
                drive_source.save(
                    update_fields=["status", "last_error", "selected_by", "updated_at"]
                )
            elif (
                drive_source.status == PodDriveHdSource.Status.IMPORTING
                and drive_source.updated_at <= timezone.now() - _IMPORT_LEASE
            ):
                drive_source.status = PodDriveHdSource.Status.PENDING
                drive_source.last_error = ""
                drive_source.selected_by = actor
                drive_source.save(
                    update_fields=["status", "last_error", "selected_by", "updated_at"]
                )
        record_event(
            action="pod.drive_hd_source.selected",
            actor=actor,
            target=drive_source,
            metadata={
                "source": source,
                "customer_public_id": str(customer.public_id),
                "drive_file_ref": self._file_ref(validated["file_id"]),
                "drive_version": validated["drive_version"],
                "created": created,
            },
        )
        return drive_source

    def import_source(self, *, source_public_id: str) -> dict:
        drive_source = (
            PodDriveHdSource.objects.select_related("customer", "selected_by", "asset_version")
            .filter(public_id=source_public_id)
            .first()
        )
        if drive_source is None:
            return {"ok": False, "error": "source_missing"}
        if (
            drive_source.status == PodDriveHdSource.Status.READY
            and drive_source.asset_version_id
            and drive_source.asset_version.customer_id == drive_source.customer_id
            and drive_source.asset_version.analysis_status == AssetVersion.AnalysisStatus.READY
        ):
            self._attach_ready_version(drive_source=drive_source)
            return {"ok": True, "status": PodDriveHdSource.Status.READY}

        claimed = self._claim_import(drive_source=drive_source)
        if not claimed:
            return {"ok": True, "status": PodDriveHdSource.Status.IMPORTING}
        drive_source.refresh_from_db()

        temporary_file = None
        try:
            gateway = self.gateway_factory()
            self._validate_source_folder(
                gateway=gateway,
                folder_id=self._source_folder_id(),
            )
            metadata = gateway.get_file_metadata(drive_source.drive_file_id)
            validated = self._validate_metadata(
                metadata=metadata,
                expected_file_id=drive_source.drive_file_id,
                gateway=gateway,
            )
            self._validate_immutable_provenance(
                drive_source=drive_source,
                validated=validated,
            )
            if drive_source.asset_version_id is None:
                temporary_file = gateway.download_file(
                    file_id=drive_source.drive_file_id,
                    max_bytes=self._max_bytes(),
                    chunk_size=_CHUNK_SIZE,
                )
                sha256, _extension, canonical_mime = self._validate_download(
                    temporary_file=temporary_file,
                    drive_source=drive_source,
                )
                version = self._create_asset_version(
                    drive_source=drive_source,
                    temporary_file=temporary_file,
                    sha256=sha256,
                    canonical_mime=canonical_mime,
                )
            else:
                version = drive_source.asset_version
            version.refresh_from_db()
            if version.analysis_status == AssetVersion.AnalysisStatus.READY:
                analyzed = version
            else:
                from apps.uploads.services.asset_analysis import AssetAnalysisService

                analyzed = AssetAnalysisService().analyze(
                    version_public_id=version.public_id,
                    source="pod.drive_hd_source",
                )
            if analyzed is None or analyzed.analysis_status != AssetVersion.AnalysisStatus.READY:
                raise ValidationError(
                    "L'analyse du fichier Drive n'a pas produit un fichier READY."
                )
            drive_source = PodDriveHdSource.objects.select_related("asset_version").get(
                pk=drive_source.pk
            )
            self._mark_ready(drive_source=drive_source, version=analyzed)
            return {"ok": True, "status": PodDriveHdSource.Status.READY}
        except Exception as exc:
            self._mark_failed(drive_source=drive_source, error=exc)
            return {"ok": False, "error": type(exc).__name__}
        finally:
            if temporary_file is not None:
                temporary_file.close()

    def _create_asset_version(
        self, *, drive_source, temporary_file, sha256, canonical_mime
    ) -> AssetVersion:
        created_file = None
        try:
            with transaction.atomic():
                locked = PodDriveHdSource.objects.select_for_update().get(pk=drive_source.pk)
                if locked.asset_version_id:
                    return locked.asset_version
                asset = Asset.objects.create(
                    customer=locked.customer,
                    created_by=locked.selected_by,
                    name=locked.original_filename,
                )
                temporary_file.seek(0)
                safe_name = get_valid_filename(Path(locked.original_filename).name) or "source"
                version = AssetVersion(
                    customer=locked.customer,
                    asset=asset,
                    uploaded_by=locked.selected_by,
                    version_number=1,
                    original_filename=locked.original_filename,
                    mime_type=canonical_mime,
                    size_bytes=locked.size_bytes,
                    sha256=sha256,
                    analysis_status=AssetVersion.AnalysisStatus.PENDING,
                )
                version.file.save(safe_name, File(temporary_file), save=False)
                created_file = (version.file.storage, version.file.name)
                version.save()
                asset.current_version = version
                asset.save(update_fields=["current_version", "updated_at"])
                locked.asset_version = version
                locked.save(update_fields=["asset_version", "updated_at"])
                return version
        except Exception:
            if created_file is not None:
                storage, name = created_file
                storage.delete(name)
            raise

    @staticmethod
    def _claim_import(*, drive_source) -> bool:
        with transaction.atomic():
            locked = PodDriveHdSource.objects.select_for_update().get(pk=drive_source.pk)
            if locked.status in {
                PodDriveHdSource.Status.READY,
            }:
                return False
            if (
                locked.status == PodDriveHdSource.Status.IMPORTING
                and locked.updated_at > timezone.now() - _IMPORT_LEASE
            ):
                return False
            locked.status = PodDriveHdSource.Status.IMPORTING
            locked.last_error = ""
            locked.save(update_fields=["status", "last_error", "updated_at"])
            return True

    def _mark_ready(self, *, drive_source, version) -> None:
        with transaction.atomic():
            locked = PodDriveHdSource.objects.select_for_update().get(pk=drive_source.pk)
            if version.customer_id != locked.customer_id:
                raise ValidationError("Le fichier importé n'appartient pas au client attendu.")
            locked.asset_version = version
            locked.status = PodDriveHdSource.Status.READY
            locked.last_error = ""
            locked.save(update_fields=["asset_version", "status", "last_error", "updated_at"])
            self._attach_ready_version(drive_source=locked)
        record_event(
            action="pod.drive_hd_source.imported",
            actor=drive_source.selected_by,
            target=drive_source,
            metadata={
                "customer_public_id": str(drive_source.customer.public_id),
                "asset_version_public_id": str(version.public_id),
            },
        )

    @staticmethod
    def _attach_ready_version(*, drive_source) -> None:
        version = drive_source.asset_version
        if (
            version is None
            or version.customer_id != drive_source.customer_id
            or version.analysis_status != AssetVersion.AnalysisStatus.READY
        ):
            return
        PodRecipeSlot.objects.filter(
            source_drive_hd=drive_source,
            recipe__variant_config__variant__product__store__customer_id=(drive_source.customer_id),
        ).update(
            source_asset_version=version,
            print_reference=version.original_filename[:255],
        )

    def _mark_failed(self, *, drive_source, error: Exception) -> None:
        message = self._public_error(error)
        PodDriveHdSource.objects.filter(pk=drive_source.pk).exclude(
            status=PodDriveHdSource.Status.READY
        ).update(
            status=PodDriveHdSource.Status.FAILED,
            last_error=message,
        )
        record_event(
            action="pod.drive_hd_source.import_failed",
            actor=drive_source.selected_by,
            target=drive_source,
            status="failure",
            message=message,
            metadata={
                "customer_public_id": str(drive_source.customer.public_id),
                "error_type": type(error).__name__,
            },
        )

    def _validate_metadata(self, *, metadata, expected_file_id: str, gateway) -> dict:
        if not metadata or str(metadata.get("id") or "") != expected_file_id:
            raise ValidationError("Fichier Drive HD introuvable.")
        folder_id = self._source_folder_id()
        if not folder_id:
            raise ValidationError("Le dossier Drive des fichiers HD n'est pas configuré.")
        if metadata.get("trashed") is not False:
            raise ValidationError("Le fichier Drive HD est supprimé ou indisponible.")
        parents = tuple(str(value) for value in (metadata.get("parents") or ()))
        if parents != (folder_id,):
            raise ValidationError("Le fichier Drive HD n'est pas dans le dossier autorisé.")
        if str(metadata.get("driveId") or "") != str(gateway.shared_drive_id):
            raise ValidationError("Le fichier Drive HD n'appartient pas au Drive partagé autorisé.")
        name = str(metadata.get("name") or "").strip()
        declared_mime_type = str(metadata.get("mimeType") or "").strip().lower()
        _extension, mime_type = normalize_dtf_metadata(name, declared_mime_type)
        try:
            size_bytes = int(metadata.get("size") or 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError("Taille du fichier Drive HD invalide.") from exc
        if size_bytes < 1 or size_bytes > self._max_bytes():
            raise ValidationError("La taille du fichier Drive HD dépasse la limite autorisée.")
        md5_checksum = str(metadata.get("md5Checksum") or "").strip().lower()
        if not _MD5_RE.fullmatch(md5_checksum):
            raise ValidationError("Checksum MD5 Drive absent ou invalide.")
        drive_version = str(metadata.get("version") or "").strip()
        if not drive_version or len(drive_version) > 64:
            raise ValidationError("Version du fichier Drive absente ou invalide.")
        return {
            "file_id": expected_file_id,
            "name": name[:255],
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "md5_checksum": md5_checksum,
            "drive_version": drive_version,
        }

    @staticmethod
    def _validate_source_folder(*, gateway, folder_id: str) -> None:
        metadata = gateway.get_file_metadata(folder_id)
        if not metadata or str(metadata.get("id") or "") != folder_id:
            raise ValidationError("Le dossier Drive des fichiers HD est introuvable.")
        if metadata.get("trashed") is not False:
            raise ValidationError("Le dossier Drive des fichiers HD est supprimé.")
        if str(metadata.get("mimeType") or "") != gateway.folder_mime_type:
            raise ValidationError("La source Drive HD configurée n'est pas un dossier.")
        if tuple(str(value) for value in (metadata.get("parents") or ())) != (
            gateway.root_folder_id,
        ):
            raise ValidationError("Le dossier Drive HD n'est pas un enfant direct de la racine.")
        if str(metadata.get("driveId") or "") != str(gateway.shared_drive_id):
            raise ValidationError("Le dossier Drive HD n'appartient pas au Drive partagé autorisé.")

    def _validate_immutable_provenance(self, *, drive_source, validated) -> None:
        if (
            validated["drive_version"] != drive_source.drive_version
            or validated["name"] != drive_source.original_filename
            or validated["mime_type"] != drive_source.mime_type
            or validated["size_bytes"] != drive_source.size_bytes
            or validated["md5_checksum"].lower() != drive_source.md5_checksum.lower()
        ):
            raise ValidationError("La source Drive a changé depuis sa sélection.")

    def _validate_download(self, *, temporary_file, drive_source) -> tuple[str, str, str]:
        temporary_file.seek(0)
        sha256 = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        size_bytes = 0
        while True:
            chunk = temporary_file.read(_CHUNK_SIZE)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > self._max_bytes():
                raise ValidationError("La taille téléchargée dépasse la limite autorisée.")
            sha256.update(chunk)
            md5.update(chunk)
        if size_bytes != drive_source.size_bytes:
            raise ValidationError("La taille téléchargée ne correspond pas aux métadonnées Drive.")
        if md5.hexdigest().lower() != drive_source.md5_checksum.lower():
            raise ValidationError("Le checksum du fichier téléchargé est invalide.")
        extension, canonical_mime = validate_dtf_document(
            temporary_file,
            drive_source.original_filename,
            drive_source.mime_type,
        )
        if canonical_mime != drive_source.mime_type and drive_source.mime_type not in {
            "application/illustrator",
            "application/vnd.adobe.illustrator",
            "application/octet-stream",
        }:
            raise ValidationError(
                "Le type réel du fichier ne correspond pas aux métadonnées Drive."
            )
        temporary_file.seek(0)
        return sha256.hexdigest(), extension, canonical_mime

    def _is_list_candidate(self, *, item, folder_id: str, gateway) -> bool:
        return bool(
            item.file_id
            and _DRIVE_FILE_ID_RE.fullmatch(item.file_id)
            and item.parents == (folder_id,)
            and item.drive_id == gateway.shared_drive_id
            and allowed_dtf_file(item.name, item.mime_type)
            and item.size is not None
            and 0 < item.size <= self._max_bytes()
            and _MD5_RE.fullmatch(item.md5_checksum or "")
        )

    @staticmethod
    def _source_folder_id() -> str:
        return str(getattr(settings, "GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID", "") or "").strip()

    @staticmethod
    def _max_bytes() -> int:
        return int(getattr(settings, "POD_DRIVE_HD_MAX_BYTES", 100 * 1024 * 1024))

    @staticmethod
    def _canonical_url(file_id: str) -> str:
        return f"https://drive.google.com/file/d/{file_id}/view"

    @staticmethod
    def _options_cache_key(*, gateway, folder_id: str) -> str:
        digest = hashlib.sha256(
            f"{gateway.shared_drive_id}:{gateway.root_folder_id}:{folder_id}".encode()
        ).hexdigest()
        return f"pod:drive-hd-options:{digest}"

    @staticmethod
    def _file_ref(file_id: str) -> str:
        return hashlib.sha256(file_id.encode()).hexdigest()[:12]

    @staticmethod
    def _public_error(error: Exception) -> str:
        if isinstance(error, ValidationError):
            messages = error.messages
            if messages:
                return str(messages[0])[:255]
        return "L'import du fichier Drive HD a échoué."

    @staticmethod
    def _audit_rejection(*, actor, customer, source: str, reason: str) -> None:
        record_event(
            action="pod.drive_hd_source.selection_rejected",
            actor=actor,
            target=customer,
            status="failure",
            message="Sélection Drive HD refusée.",
            metadata={"source": source, "reason": reason},
        )
