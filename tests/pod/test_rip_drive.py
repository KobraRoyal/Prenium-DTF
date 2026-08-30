from __future__ import annotations

import pytest
from apps.pod.services.rip_drive import PodRipDriveSyncService
from apps.pod.services.rip_lots import PodRipLotService

from tests.pod.test_rip_lots import configure_pod
from tests.pod.test_variant_config import MANAGE, pod_fixture, staff_client

pytestmark = pytest.mark.django_db

rip = PodRipLotService()


class FakeDriveGateway:
    def __init__(self):
        self.folders: dict[str, str] = {}
        self.uploads: list[str] = []
        self._n = 0

    def ensure_folder(self, *, parent_id: str, name: str) -> str:
        key = f"{parent_id}/{name}"
        if key not in self.folders:
            self._n += 1
            self.folders[key] = f"fld-{self._n}"
        return self.folders[key]

    def upload_file(self, *, parent_id: str, name: str, mime_type: str, content: bytes) -> str:
        self.uploads.append(name)
        return f"file-{name}"


def test_rip_drive_sync_uploads_flat_projection(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.GOOGLE_DRIVE_SYNC_ENABLED = True
    settings.GOOGLE_DRIVE_ROOT_FOLDER_ID = "root-drive"
    actor, _client = staff_client(email="staff-drive@example.com", permissions=MANAGE)
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-DRIVE",
    )
    lot = rip.prepare_dtf_lot(actor=actor, source="test")
    gateway = FakeDriveGateway()
    result = PodRipDriveSyncService().sync_lot(lot=lot, actor=actor, gateway=gateway)
    lot.refresh_from_db()
    assert result["skipped"] is False
    assert lot.drive_file_count >= 2
    assert lot.drive_folder_id
    assert lot.drive_error == ""
    assert "manifest.json" in gateway.uploads


def test_rip_drive_skipped_when_flag_off(settings):
    settings.GOOGLE_DRIVE_SYNC_ENABLED = False
    actor, _client = staff_client(email="staff-drive-off@example.com", permissions=MANAGE)
    dtf, _blank, _blank_variant, _variant = pod_fixture(actor=actor)
    from apps.pod.models import PodRipLot

    lot = PodRipLot.objects.create(
        code="lot-off",
        technique=dtf,
        nas_relative_path="x/lot-off",
        prepared_by=actor,
        file_count=0,
    )
    result = PodRipDriveSyncService().sync_lot(lot=lot, actor=actor, gateway=FakeDriveGateway())
    assert result["skipped"] is True
