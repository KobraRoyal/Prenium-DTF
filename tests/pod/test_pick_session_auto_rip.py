from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from apps.pod.models import PodRipLot, PodRipWorkItem, PodUnit
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.rip_drive import PodRipDriveSyncService
from apps.pod.tasks import prepare_pick_session_rip_and_drive_task
from django.test import override_settings

from tests.pod.test_rip_lots import configure_pod, rip
from tests.pod.test_shopify_ingest import _stock_picking_blank
from tests.pod.test_variant_config import MANAGE, pod_fixture, staff_client

pytestmark = pytest.mark.django_db(transaction=True)

picking = PodPickSessionService()


@override_settings(POD_AUTO_RIP_ON_PICK_SESSION=True, GOOGLE_DRIVE_SYNC_ENABLED=True)
def test_open_session_auto_prepares_rip_and_syncs_drive(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    settings.GOOGLE_DRIVE_ROOT_FOLDER_ID = "root-drive"
    actor, _client = staff_client(
        email="staff-auto-rip@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=2)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-AUTO-RIP",
        quantity=1,
    )
    with patch.object(
        PodRipDriveSyncService,
        "sync_lot",
        side_effect=lambda *, lot, actor=None, gateway=None: {
            "skipped": False,
            "files": 1,
            "folder": "fld-test",
        },
    ) as sync_mock:
        session = picking.open_session(
            actor=actor,
            source="test",
            work_item_public_ids=[str(item.public_id)],
        )
    lot = PodRipLot.objects.get(nas_relative_path=session.code)
    assert lot.file_count >= 1
    assert lot.units.count() == 1
    item.refresh_from_db()
    assert item.status == PodRipWorkItem.Status.INCLUDED
    assert PodUnit.objects.filter(scan_identifier=session.lines.get().scan_identifier).exists()
    sync_mock.assert_called_once()
    rip_dir = Path(tmp_path) / "pod_rip" / session.code / "02_rip"
    assert rip_dir.is_dir()
    assert any(p.is_file() for p in rip_dir.iterdir())


@override_settings(POD_AUTO_RIP_ON_PICK_SESSION=True)
def test_prepare_pick_session_task_is_idempotent(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-auto-rip-idem@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=2)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-AUTO-IDEM",
        quantity=1,
    )
    session = picking.open_session(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    result = prepare_pick_session_rip_and_drive_task(
        session_public_id=str(session.public_id),
        actor_id=actor.pk,
    )
    assert result["ok"] is True
    lot_id = result["lot_public_id"]
    with patch("apps.pod.services.rip_lots.PodRipLotService._enqueue_drive_sync") as resync:
        again = prepare_pick_session_rip_and_drive_task(
            session_public_id=str(session.public_id),
            actor_id=actor.pk,
        )
    assert again["ok"] is True
    assert again["lot_public_id"] == lot_id
    resync.assert_called_once()
    assert PodRipLot.objects.filter(nas_relative_path=session.code).count() == 1
