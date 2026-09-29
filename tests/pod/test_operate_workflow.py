from __future__ import annotations

import pytest
from apps.pod.models import PodPickSessionLine, PodRipLot
from apps.pod.services.operate_workflow import PodOperateWorkflowService
from apps.pod.services.pick_sessions import PodPickSessionService
from apps.pod.services.pose import PodPoseService
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.pod.test_rip_lots import configure_pod, open_pick_session_for_items, rip
from tests.pod.test_shopify_ingest import _stock_picking_blank
from tests.pod.test_variant_config import MANAGE, pod_fixture, staff_client

pytestmark = pytest.mark.django_db

operate = PodOperateWorkflowService()
picking = PodPickSessionService()
pose = PodPoseService()


def test_operate_rail_and_print_confirm_unlocks_pose(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(
        email="staff-operate@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=2)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-OPERATE",
        quantity=1,
    )
    session, location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    lot = rip.prepare_dtf_for_pick_session(actor=actor, session=session, source="test")
    assert lot is not None
    scan = session.lines.get().scan_identifier

    rail = operate.session_rail(session=session)
    assert rail is not None
    assert rail[1].key == "print" and rail[1].state == "active"

    with pytest.raises(ValidationError, match="Impression DTF non validée"):
        pose.lookup(actor=actor, scan_identifier=scan)

    operate.confirm_dtf_print(actor=actor, session=session, source="test")
    lot.refresh_from_db()
    assert lot.operator_print_confirmed_at is not None

    with pytest.raises(ValidationError, match="support n.est pas encore sorti"):
        pose.lookup(actor=actor, scan_identifier=scan)

    picking.confirm_pick(
        actor=actor,
        source="test",
        scan_identifier=scan,
        scanned_bin_code=location.code,
    )
    looked = pose.lookup(actor=actor, scan_identifier=scan)
    assert looked["unit"].scan_identifier == scan

    response = client.post(
        reverse("portal:staff-pod-hub"),
        {
            "intent": "confirm_dtf_print",
            "session_public_id": str(session.public_id),
        },
    )
    assert response.status_code == 302
    rail_after = operate.session_rail(session=session)
    assert rail_after[0].state == "done"
    assert rail_after[1].state == "done"
    assert rail_after[2].state == "active"


def test_operate_board_lists_session_stage(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, client = staff_client(
        email="staff-suivi@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=2)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-SUIVI",
        quantity=1,
    )
    session, _location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    board = operate.board(actor=actor, stage="all")
    assert board["active_count"] >= 1
    assert any(row.session.public_id == session.public_id and row.stage == "pick" for row in board["rows"])
    page = client.get(reverse("portal:staff-pod-suivi"))
    assert page.status_code == 200
    body = page.content.decode()
    assert session.code in body
    assert "Suivi POD" in body
    assert "pod-suivi-kpis" in body


def test_suivi_sync_drive_enqueues_without_inline_sync(tmp_path, settings, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    settings.GOOGLE_DRIVE_SYNC_ENABLED = True
    actor, client = staff_client(
        email="staff-suivi-drive@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    _stock_picking_blank(actor=actor, blank_variant=blank_variant, quantity=2)
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-SUIVI-DRIVE",
        quantity=1,
    )
    session, _location = open_pick_session_for_items(
        actor=actor,
        blank_variant=blank_variant,
        items=[item],
    )
    lot = rip.prepare_dtf_for_pick_session(actor=actor, session=session, source="test")
    assert lot is not None
    called: list[str] = []

    def _fake_delay(lot_public_id: str):
        called.append(lot_public_id)

    monkeypatch.setattr(
        "apps.pod.tasks.sync_pod_rip_lot_to_drive_task.delay",
        _fake_delay,
    )
    response = client.post(
        reverse("portal:staff-pod-suivi"),
        {
            "intent": "sync_drive",
            "lot_public_id": str(lot.public_id),
            "session_public_id": str(session.public_id),
        },
    )
    assert response.status_code == 302
    assert called == [str(lot.public_id)]


def test_hub_board_avoids_loading_waiting_units(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    actor, _client = staff_client(
        email="staff-hub-light@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    board = rip.production_board(actor=actor)
    assert board["waiting_units"] == []
    assert board["press_page_obj"] is None
    assert board["press_count"] == 0
    light = list(rip.list_queue(actor=actor, light=True)[:5])
    assert light == []
