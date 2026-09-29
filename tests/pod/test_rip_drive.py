from __future__ import annotations

import pytest
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.rip_drive import PodRipDriveSyncService
from apps.pod.services.rip_lots import PodRipLotService

from tests.pod.test_rip_lots import configure_pod
from tests.pod.test_shopify_ingest import _stock_picking_blank
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
    actor, _client = staff_client(
        email="staff-drive@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=1)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-DRIVE",
    )
    picking = PodPickSessionService()
    session = picking.open_session(
        actor=actor, source="test", work_item_public_ids=[str(item.public_id)]
    )
    picking.confirm_pick(
        actor=actor,
        source="test",
        scan_identifier=session.lines.get().scan_identifier,
        scanned_bin_code="A-01-01-A",
    )
    lot = rip.prepare_dtf_lot(actor=actor, source="test")
    gateway = FakeDriveGateway()
    result = PodRipDriveSyncService().sync_lot(lot=lot, actor=actor, gateway=gateway)
    lot.refresh_from_db()
    assert result["skipped"] is False
    assert lot.drive_file_count >= 1
    assert lot.drive_folder_id
    assert lot.drive_error == ""
    assert any(name.endswith(".png") for name in gateway.uploads)
    assert "manifest.json" not in gateway.uploads
    assert any(session.code in key for key in gateway.folders)


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
