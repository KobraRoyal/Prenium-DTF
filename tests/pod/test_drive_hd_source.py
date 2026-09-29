import base64
import hashlib
import json
import tempfile
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.pod.models import (
    IdsVariantConfig,
    PodDriveHdSource,
    PodRecipe,
    PodRecipeSlot,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.drive_hd_sources import DriveHdSourceService
from apps.pod.services.hd_formats import (
    allowed_dtf_file,
    validate_dtf_document,
    validate_dtf_header,
)
from apps.pod.services.variant_config import VariantConfigService
from apps.pod.tasks import recover_pod_drive_hd_sources_task
from apps.uploads.models import Asset, AssetVersion
from apps.uploads.services.drive import DriveRemoteFile
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from PIL import Image

pytestmark = pytest.mark.django_db

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAF"
    "AAH/iZk9HQAAAABJRU5ErkJggg=="
)


def _pdf_bytes(*, pages=1):
    document = pymupdf.open()
    try:
        for _index in range(pages):
            document.new_page(width=72, height=72)
        return document.tobytes()
    finally:
        document.close()


def _tiff_bytes(*, frames=1):
    output = BytesIO()
    images = [Image.new("RGBA", (2, 2), (255, 0, 0, 128)) for _index in range(frames)]
    images[0].save(output, format="TIFF", save_all=frames > 1, append_images=images[1:])
    return output.getvalue()


PDF_BYTES = _pdf_bytes()
TIFF_BYTES = _tiff_bytes()
POSTSCRIPT_BYTES = b"""%!PS-Adobe-3.0 EPSF-3.0
%%BoundingBox: 0 0 10 10
%%Pages: 1
%%Page: 1 1
newpath 0 0 moveto 10 10 lineto stroke
showpage
%%EOF
"""
FILE_ID = "drive_png_source_123"
FOLDER_ID = "drive_hd_folder_123"
ROOT_ID = "drive_shared_root_123"
SHARED_DRIVE_ID = "shared_drive_123"


def manager(email="drive-manager@example.com"):
    actor = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    actor.user_permissions.add(
        Permission.objects.get(codename="manage_pod_catalog"),
        Permission.objects.get(codename="access_staff_portal"),
    )
    return actor


class FakeGateway:
    shared_drive_id = SHARED_DRIVE_ID
    root_folder_id = ROOT_ID
    folder_mime_type = "application/vnd.google-apps.folder"

    def __init__(
        self,
        *,
        file_parent=FOLDER_ID,
        file_drive=SHARED_DRIVE_ID,
        file_name="visuel-hd.png",
        file_mime="image/png",
        content=PNG_BYTES,
    ):
        self.file_parent = file_parent
        self.file_drive = file_drive
        self.file_name = file_name
        self.file_mime = file_mime
        self.content = content
        self.list_calls = []

    @property
    def file_metadata(self):
        return {
            "id": FILE_ID,
            "name": self.file_name,
            "trashed": False,
            "mimeType": self.file_mime,
            "size": str(len(self.content)),
            "md5Checksum": hashlib.md5(self.content, usedforsecurity=False).hexdigest(),
            "version": "42",
            "parents": [self.file_parent],
            "driveId": self.file_drive,
        }

    def get_file_metadata(self, file_id):
        if file_id == FOLDER_ID:
            return {
                "id": FOLDER_ID,
                "name": "HD_POD_Fichier Ok Prod",
                "trashed": False,
                "mimeType": self.folder_mime_type,
                "parents": [ROOT_ID],
                "driveId": SHARED_DRIVE_ID,
            }
        if file_id == FILE_ID:
            return self.file_metadata
        return None

    def list_binary_files(self, *, parent_id, page_token=None, page_size=100):
        self.list_calls.append((parent_id, page_token, page_size))
        return (
            [
                DriveRemoteFile(
                    file_id=FILE_ID,
                    name=self.file_name,
                    mime_type=self.file_mime,
                    size=len(self.content),
                    md5_checksum=self.file_metadata["md5Checksum"],
                    parents=(FOLDER_ID,),
                    drive_id=SHARED_DRIVE_ID,
                )
            ],
            None,
        )

    def download_file(self, *, file_id, max_bytes, chunk_size):
        assert file_id == FILE_ID
        assert len(self.content) <= max_bytes
        temporary_file = tempfile.TemporaryFile(mode="w+b")
        temporary_file.write(self.content)
        temporary_file.seek(0)
        return temporary_file


@pytest.fixture(autouse=True)
def drive_settings(settings):
    settings.GOOGLE_DRIVE_POD_HD_SOURCE_FOLDER_ID = FOLDER_ID
    settings.POD_DRIVE_HD_MAX_BYTES = 1024 * 1024


@pytest.mark.parametrize(
    ("name", "mime_type", "content", "expected_mime"),
    [
        ("production.png", "image/png", PNG_BYTES, "image/png"),
        ("production finale.pdf", "application/pdf", PDF_BYTES, "application/pdf"),
        ("production.ai", "application/pdf", PDF_BYTES, "application/pdf"),
        ("production.ai", "application/illustrator", PDF_BYTES, "application/pdf"),
        ("production.ai", "application/octet-stream", PDF_BYTES, "application/pdf"),
        (
            "production.ai",
            "application/vnd.adobe.illustrator",
            POSTSCRIPT_BYTES,
            "application/postscript",
        ),
        (
            "production.eps",
            "application/postscript",
            POSTSCRIPT_BYTES,
            "application/postscript",
        ),
        ("production.tif", "image/tiff", TIFF_BYTES, "image/tiff"),
        ("production.tiff", "application/octet-stream", TIFF_BYTES, "image/tiff"),
    ],
)
def test_dtf_formats_are_imported_as_unchanged_originals(
    monkeypatch,
    settings,
    tmp_path,
    name,
    mime_type,
    content,
    expected_mime,
):
    settings.MEDIA_ROOT = tmp_path
    actor = manager(email=f"manager-{Path(name).suffix[1:]}@example.com")
    customer = Customer.objects.create(name=f"Client {name}")
    gateway = FakeGateway(file_name=name, file_mime=mime_type, content=content)
    service = DriveHdSourceService(gateway_factory=lambda: gateway)
    source = service.select(
        customer=customer,
        drive_file_id=FILE_ID,
        actor=actor,
        source="test",
    )

    def ready_analysis(_self, *, version_public_id, source):
        version = AssetVersion.objects.get(public_id=version_public_id)
        version.analysis_status = AssetVersion.AnalysisStatus.READY
        version.save(update_fields=["analysis_status", "updated_at"])
        return version

    monkeypatch.setattr(
        "apps.uploads.services.asset_analysis.AssetAnalysisService.analyze",
        ready_analysis,
    )

    assert service.import_source(source_public_id=str(source.public_id)) == {
        "ok": True,
        "status": PodDriveHdSource.Status.READY,
    }
    source.refresh_from_db()
    version = source.asset_version
    version.file.open("rb")
    try:
        stored_content = version.file.read()
    finally:
        version.file.close()
    assert version.original_filename == name
    assert version.mime_type == expected_mime
    assert version.size_bytes == len(content)
    assert version.sha256 == hashlib.sha256(content).hexdigest()
    assert stored_content == content


@pytest.mark.parametrize(
    ("name", "mime_type", "header"),
    [
        ("production.svg", "image/svg+xml", b"<svg>"),
        ("production.psd", "image/vnd.adobe.photoshop", b"8BPS"),
        ("production.pdf", "image/png", b"%PDF-1.7"),
        ("production.png", "image/png", b"%PDF-1.7"),
        ("production.eps", "application/postscript", b"%PDF-1.7"),
        ("production.ai", "application/pdf", b"%!PS-Adobe-3.0"),
    ],
)
def test_dtf_policy_rejects_extension_mime_and_signature_mismatches(name, mime_type, header):
    if allowed_dtf_file(name, mime_type):
        with pytest.raises(ValidationError):
            validate_dtf_header(name, mime_type, header)
    else:
        assert allowed_dtf_file(name, mime_type) is False
        with pytest.raises(ValidationError):
            validate_dtf_header(name, mime_type, header)


@pytest.mark.parametrize(
    ("name", "mime_type", "content"),
    [
        ("multipage.pdf", "application/pdf", _pdf_bytes(pages=2)),
        ("multipage.ai", "application/pdf", _pdf_bytes(pages=2)),
        ("multipage.tiff", "image/tiff", _tiff_bytes(frames=2)),
        (
            "multipage.eps",
            "application/postscript",
            POSTSCRIPT_BYTES.replace(b"%%Pages: 1", b"%%Pages: 2") + b"%%Page: 2 2\nshowpage\n",
        ),
    ],
)
def test_dtf_policy_rejects_multipage_documents(name, mime_type, content):
    with pytest.raises(ValidationError, match="exactement une|multipage"):
        validate_dtf_document(BytesIO(content), name, mime_type)


def test_ai_postscript_is_supported_and_validated_by_sandboxed_renderer():
    assert validate_dtf_document(
        BytesIO(POSTSCRIPT_BYTES),
        "production.ai",
        "application/postscript",
    ) == (".ai", "application/postscript")


@pytest.mark.parametrize(
    "content",
    [
        (
            b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 10 10\n"
            b"newpath 0 0 moveto 10 10 lineto stroke\nshowpage\nshowpage\n%%EOF\n"
        ),
        (
            b"%!PS-Adobe-3.0 EPSF-3.0\n%%Pages: (atend)\n"
            b"newpath 0 0 moveto 10 10 lineto stroke\nshowpage\nshowpage\n"
            b"%%Trailer\n%%Pages: 1\n%%EOF\n"
        ),
        POSTSCRIPT_BYTES.replace(b"%%Pages: 1", b"%%Pages: 1\n%%Page: 2 2") + b"showpage\n",
    ],
)
def test_dtf_postscript_rejects_hidden_extra_pages(content):
    with pytest.raises(ValidationError, match="exactement une page"):
        validate_dtf_document(BytesIO(content), "production.eps", "application/postscript")


def test_library_requires_manager_and_validates_configured_folder():
    gateway = FakeGateway()
    service = DriveHdSourceService(gateway_factory=lambda: gateway)
    readonly = get_user_model().objects.create_user(
        email="drive-readonly@example.com", password="pass", is_staff=True
    )

    hidden = service.list_options(actor=readonly)
    visible = service.list_options(actor=manager())

    assert hidden.options == ()
    assert gateway.list_calls == [(FOLDER_ID, None, 100)]
    assert [(item.file_id, item.name) for item in visible.options] == [(FILE_ID, "visuel-hd.png")]


def test_selection_revalidates_exact_parent_and_audits_rejection():
    actor = manager()
    customer = Customer.objects.create(name="Client Drive")
    gateway = FakeGateway(file_parent="foreign-folder")
    service = DriveHdSourceService(gateway_factory=lambda: gateway)

    with pytest.raises(ValidationError, match="dossier autorisé"):
        service.select(
            customer=customer,
            drive_file_id=FILE_ID,
            actor=actor,
            source="test",
        )

    assert not PodDriveHdSource.objects.exists()
    assert AuditLogEntry.objects.filter(
        action="pod.drive_hd_source.selection_rejected",
        status=AuditLogEntry.Status.FAILURE,
    ).exists()


def test_drive_network_error_returns_safe_picker_state_and_validation_error():
    actor = manager(email="drive-network@example.com")
    customer = Customer.objects.create(name="Client réseau")

    class OfflineGateway(FakeGateway):
        def get_file_metadata(self, file_id):
            raise OSError("private transport detail")

    service = DriveHdSourceService(gateway_factory=OfflineGateway)
    cache.delete(service._options_cache_key(gateway=OfflineGateway(), folder_id=FOLDER_ID))
    options = service.list_options(actor=actor)

    assert options.options == ()
    assert options.configured is True
    assert options.error == "La bibliothèque Drive HD est temporairement indisponible."
    with pytest.raises(ValidationError, match="Impossible de valider le fichier Drive HD"):
        service.select(
            customer=customer,
            drive_file_id=FILE_ID,
            actor=actor,
            source="test",
        )
    assert not PodDriveHdSource.objects.exists()


def test_non_staff_with_direct_permission_cannot_list_or_select():
    actor = get_user_model().objects.create_user(
        email="drive-not-staff@example.com", password="pass", is_staff=False
    )
    actor.user_permissions.add(
        Permission.objects.get(codename="manage_pod_catalog"),
        Permission.objects.get(codename="access_staff_portal"),
    )
    customer = Customer.objects.create(name="Client privé")
    service = DriveHdSourceService(gateway_factory=FakeGateway)

    with pytest.raises(PermissionDenied):
        service.list_options(actor=actor)
    with pytest.raises(PermissionDenied):
        service.select(
            customer=customer,
            drive_file_id=FILE_ID,
            actor=actor,
            source="test",
        )

    assert not PodDriveHdSource.objects.exists()
    assert (
        AuditLogEntry.objects.filter(
            action="pod.drive_hd_source.permission_rejected",
            status=AuditLogEntry.Status.FAILURE,
        ).count()
        == 2
    )


def test_failed_database_insert_removes_imported_blob(monkeypatch, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    actor = manager()
    customer = Customer.objects.create(name="Client stockage")
    service = DriveHdSourceService(gateway_factory=FakeGateway)
    source = service.select(
        customer=customer,
        drive_file_id=FILE_ID,
        actor=actor,
        source="test",
    )

    def fail_save(*_args, **_kwargs):
        raise RuntimeError("database insert failed")

    monkeypatch.setattr(AssetVersion, "save", fail_save)
    result = service.import_source(source_public_id=str(source.public_id))

    assert result == {"ok": False, "error": "RuntimeError"}
    assert AssetVersion.objects.count() == 0
    assert not list(tmp_path.rglob("*.png"))


def test_import_is_idempotent_and_attaches_only_same_customer_slots(monkeypatch):
    actor = manager()
    customer = Customer.objects.create(name="Client A")
    other_customer = Customer.objects.create(name="Client B")
    gateway = FakeGateway()
    service = DriveHdSourceService(gateway_factory=lambda: gateway)
    source = service.select(
        customer=customer,
        drive_file_id=FILE_ID,
        actor=actor,
        source="test",
    )
    other_source = service.select(
        customer=other_customer,
        drive_file_id=FILE_ID,
        actor=actor,
        source="test",
    )
    technique = PrintTechnique.objects.create(code="dtf-drive", name="DTF Drive")
    own_slot = _slot_for_customer(
        customer=customer,
        suffix="a",
        technique=technique,
        source=source,
    )
    foreign_slot = _slot_for_customer(
        customer=other_customer,
        suffix="b",
        technique=technique,
        source=source,
    )
    with pytest.raises(ValidationError, match="source Drive HD doit appartenir"):
        foreign_slot.full_clean()

    def ready_analysis(_self, *, version_public_id, source):
        version = AssetVersion.objects.get(public_id=version_public_id)
        version.analysis_status = AssetVersion.AnalysisStatus.READY
        version.save(update_fields=["analysis_status", "updated_at"])
        return version

    monkeypatch.setattr(
        "apps.uploads.services.asset_analysis.AssetAnalysisService.analyze",
        ready_analysis,
    )

    first = service.import_source(source_public_id=str(source.public_id))
    second = service.import_source(source_public_id=str(source.public_id))

    source.refresh_from_db()
    own_slot.refresh_from_db()
    foreign_slot.refresh_from_db()
    assert first == {"ok": True, "status": PodDriveHdSource.Status.READY}
    assert second == first
    assert source.asset_version.customer == customer
    assert own_slot.source_asset_version == source.asset_version
    assert foreign_slot.source_asset_version is None
    assert other_source.customer == other_customer
    assert other_source.pk != source.pk
    assert Asset.objects.for_customer(customer).count() == 1
    assert Asset.objects.for_customer(other_customer).count() == 0


def _slot_for_customer(*, customer, suffix, technique, source):
    store = ShopifyStore.objects.create(
        customer=customer,
        slug=f"drive-store-{suffix}",
        name=f"Drive store {suffix}",
        shop_domain=f"drive-store-{suffix}.myshopify.com",
    )
    product = ShopifyProduct.objects.create(
        store=store,
        external_id=f"product-{suffix}",
        title=f"Produit {suffix}",
    )
    variant = ShopifyVariant.objects.create(
        product=product,
        external_id=f"variant-{suffix}",
        title=f"Variante {suffix}",
    )
    config = IdsVariantConfig.objects.create(variant=variant, mode=IdsVariantConfig.Mode.POD)
    recipe = PodRecipe.objects.create(variant_config=config)
    return PodRecipeSlot.objects.create(
        recipe=recipe,
        placement="front",
        technique=technique,
        source_drive_hd=source,
    )


def test_dispatch_failure_is_recovered_without_republishing_fresh_or_failed(monkeypatch):
    actor = manager()
    service = DriveHdSourceService(gateway_factory=FakeGateway)
    technique = PrintTechnique.objects.create(code="dtf-recovery", name="DTF Recovery")
    sources = []
    for suffix in ("lost", "fresh", "failed"):
        customer = Customer.objects.create(name=f"Client {suffix}")
        source = service.select(
            customer=customer,
            drive_file_id=FILE_ID,
            actor=actor,
            source="test",
        )
        _slot_for_customer(customer=customer, suffix=suffix, technique=technique, source=source)
        sources.append(source)
    lost, fresh, failed = sources
    selected_metadata = (
        AuditLogEntry.objects.filter(
            action="pod.drive_hd_source.selected", target_public_id=lost.public_id
        )
        .get()
        .metadata
    )
    assert FILE_ID not in json.dumps(selected_metadata)
    assert lost.canonical_url not in json.dumps(selected_metadata)
    PodDriveHdSource.objects.filter(pk=lost.pk).update(
        updated_at=timezone.now() - timedelta(minutes=3)
    )
    PodDriveHdSource.objects.filter(pk=failed.pk).update(
        status=PodDriveHdSource.Status.FAILED,
        updated_at=timezone.now() - timedelta(minutes=3),
    )

    def broker_unavailable(_public_id):
        raise ConnectionError("broker unavailable")

    VariantConfigService._enqueue_drive_import(
        task=SimpleNamespace(delay=broker_unavailable),
        source_public_id=str(lost.public_id),
        drive_source=lost,
        actor=actor,
        source="test",
    )
    dispatched = []
    monkeypatch.setattr("apps.pod.tasks.import_pod_drive_hd_source_task.delay", dispatched.append)

    result = recover_pod_drive_hd_sources_task()

    assert result == {"due": 1, "dispatched": 1}
    assert dispatched == [str(lost.public_id)]
    assert recover_pod_drive_hd_sources_task() == {"due": 1, "dispatched": 0}
    assert dispatched == [str(lost.public_id)]
    assert AuditLogEntry.objects.filter(action="pod.drive_hd_source.dispatch_failed").exists()
    fresh.refresh_from_db()
    failed.refresh_from_db()
    assert fresh.status == PodDriveHdSource.Status.PENDING
    assert failed.status == PodDriveHdSource.Status.FAILED

    PodDriveHdSource.objects.filter(pk=lost.pk).update(
        status=PodDriveHdSource.Status.IMPORTING,
        updated_at=timezone.now() - timedelta(minutes=17),
    )
    cache.delete(f"pod:drive_hd_recovery:{lost.public_id}")
    assert recover_pod_drive_hd_sources_task() == {"due": 1, "dispatched": 1}
    assert dispatched == [str(lost.public_id), str(lost.public_id)]


def test_recovery_releases_publication_lock_if_broker_rejects(monkeypatch):
    actor = manager(email="drive-recovery-failure@example.com")
    customer = Customer.objects.create(name="Client reprise")
    source = DriveHdSourceService(gateway_factory=FakeGateway).select(
        customer=customer, drive_file_id=FILE_ID, actor=actor, source="test"
    )
    technique = PrintTechnique.objects.create(code="dtf-retry", name="DTF Retry")
    _slot_for_customer(customer=customer, suffix="retry", technique=technique, source=source)
    PodDriveHdSource.objects.filter(pk=source.pk).update(
        updated_at=timezone.now() - timedelta(minutes=3)
    )

    def broker_unavailable(_public_id):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr("apps.pod.tasks.import_pod_drive_hd_source_task.delay", broker_unavailable)
    assert recover_pod_drive_hd_sources_task() == {"due": 1, "dispatched": 0}
    assert AuditLogEntry.objects.filter(
        action="pod.drive_hd_source.recovery_dispatch_failed"
    ).exists()

    dispatched = []
    monkeypatch.setattr("apps.pod.tasks.import_pod_drive_hd_source_task.delay", dispatched.append)
    assert recover_pod_drive_hd_sources_task() == {"due": 1, "dispatched": 1}
    assert dispatched == [str(source.public_id)]
