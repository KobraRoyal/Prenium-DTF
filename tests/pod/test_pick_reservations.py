from __future__ import annotations

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.inventory.models import (
    SkuKind,
    StockBalance,
    StockMovement,
    StockOwnerKind,
    WarehouseZone,
)
from apps.inventory.services import StockOpsService, WarehouseLayoutService
from apps.pod.models import PodPickSession, PodPickSessionLine
from apps.pod.services.pick_sessions import PodPickSessionService
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.pod.test_catalog_and_warehouse import MANAGE, staff_client
from tests.pod.test_rip_lots import configure_pod, rip
from tests.pod.test_variant_config import pod_fixture

pytestmark = pytest.mark.django_db

pick_sessions = PodPickSessionService()
stock = StockOpsService()
warehouse = WarehouseLayoutService()


def _queued_with_stock(*, actor, quantity: int, stock_quantity: int):
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    warehouse.ensure_default_layout(actor=actor)
    zone = WarehouseZone.objects.get(kind=WarehouseZone.Kind.BLANKS, warehouse__code="atl-01")
    location = warehouse.create_location(
        actor=actor,
        source="test",
        data={
            "zone_public_id": str(zone.public_id),
            "code": "A-01-01-P",
            "label": "Picking POD",
        },
    )
    warehouse.set_blank_default_location(
        actor=actor,
        source="test",
        variant_public_id=blank_variant.public_id,
        location_public_id=location.public_id,
    )
    if stock_quantity:
        balance = stock.receive_blank(
            actor=actor,
            source="test",
            blank_variant_public_id=blank_variant.public_id,
            location_public_id=location.public_id,
            quantity=stock_quantity,
        )
    else:
        balance = None
    item = rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-RESERVE",
        quantity=quantity,
    )
    return item, blank_variant, location, balance


def test_open_session_reserves_and_scan_consumes_exactly_once():
    actor, _client = staff_client(email="staff-pick-reserve@example.com", permissions=MANAGE)
    item, _blank_variant, location, balance = _queued_with_stock(
        actor=actor, quantity=2, stock_quantity=2
    )

    session = pick_sessions.open_session(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )

    balance.refresh_from_db()
    assert balance.qty_on_hand == 2
    assert balance.qty_reserved == 2
    assert set(session.lines.values_list("reservation_status", flat=True)) == {
        PodPickSessionLine.ReservationStatus.RESERVED
    }
    line = session.lines.order_by("sequence").first()
    with pytest.raises(ValidationError, match="Bin incorrect"):
        pick_sessions.confirm_pick(
            actor=actor,
            source="test",
            scan_identifier=line.scan_identifier,
            scanned_bin_code="WRONG-BIN",
        )
    picked = pick_sessions.confirm_pick(
        actor=actor,
        source="test",
        scan_identifier=line.scan_identifier,
        scanned_bin_code=location.code.lower(),
    )
    assert picked.reservation_status == PodPickSessionLine.ReservationStatus.PICKED
    assert picked.picked_by == actor
    balance.refresh_from_db()
    assert (balance.qty_on_hand, balance.qty_reserved) == (1, 1)
    assert StockMovement.objects.filter(kind=StockMovement.Kind.PICK).count() == 1

    # A scanner retry is idempotent and cannot debit the blank twice.
    pick_sessions.confirm_pick(
        actor=actor,
        source="test",
        scan_identifier=line.scan_identifier,
        scanned_bin_code=location.code,
    )
    balance.refresh_from_db()
    assert (balance.qty_on_hand, balance.qty_reserved) == (1, 1)
    assert StockMovement.objects.filter(kind=StockMovement.Kind.PICK).count() == 1
    assert AuditLogEntry.objects.filter(action="pod.pick.line_picked").count() == 1


def test_open_session_rolls_back_all_reservations_when_stock_is_short():
    actor, _client = staff_client(email="staff-pick-short@example.com", permissions=MANAGE)
    item, _blank_variant, _location, balance = _queued_with_stock(
        actor=actor, quantity=3, stock_quantity=2
    )

    with pytest.raises(ValidationError, match="POD-18"):
        pick_sessions.open_session(
            actor=actor,
            source="test",
            work_item_public_ids=[str(item.public_id)],
        )

    balance.refresh_from_db()
    assert (balance.qty_on_hand, balance.qty_reserved) == (2, 0)
    assert PodPickSession.objects.count() == 0
    assert PodPickSessionLine.objects.count() == 0


def test_void_releases_reserved_but_never_returns_picked_stock():
    actor, _client = staff_client(email="staff-pick-void@example.com", permissions=MANAGE)
    item, _blank_variant, location, balance = _queued_with_stock(
        actor=actor, quantity=2, stock_quantity=2
    )
    session = pick_sessions.open_session(
        actor=actor,
        source="test",
        work_item_public_ids=[str(item.public_id)],
    )
    first = session.lines.order_by("sequence").first()
    pick_sessions.confirm_pick(
        actor=actor,
        source="test",
        scan_identifier=first.scan_identifier,
        scanned_bin_code=location.code,
    )

    assert pick_sessions.void_lines_for_work_item(work_item=item, reason="commande annulée") == 2

    balance.refresh_from_db()
    assert (balance.qty_on_hand, balance.qty_reserved) == (1, 0)
    statuses = set(session.lines.values_list("reservation_status", flat=True))
    assert statuses == {
        PodPickSessionLine.ReservationStatus.PICKED,
        PodPickSessionLine.ReservationStatus.RELEASED,
    }
    assert session.lines.filter(voided_at__isnull=True).count() == 0
    assert StockMovement.objects.filter(kind=StockMovement.Kind.PICK).count() == 1


def test_customer_owned_balance_cannot_fund_atelier_pick_session():
    actor, _client = staff_client(email="staff-pick-tenant@example.com", permissions=MANAGE)
    item, blank_variant, location, _balance = _queued_with_stock(
        actor=actor, quantity=1, stock_quantity=0
    )
    customer = Customer.objects.create(name="Stock locataire A")
    customer_balance = StockBalance.objects.create(
        sku_kind=SkuKind.BLANK,
        blank_variant=blank_variant,
        finished_sku="",
        location=location,
        owner_kind=StockOwnerKind.CUSTOMER,
        customer=customer,
        qty_on_hand=10,
        qty_reserved=0,
    )

    with pytest.raises(ValidationError, match="POD-18"):
        pick_sessions.open_session(
            actor=actor,
            source="test",
            work_item_public_ids=[str(item.public_id)],
        )

    customer_balance.refresh_from_db()
    assert (customer_balance.qty_on_hand, customer_balance.qty_reserved) == (10, 0)
    assert PodPickSessionLine.objects.count() == 0


def test_legacy_untracked_session_can_be_soft_voided_then_reprinted_without_stock_movement():
    actor, client = staff_client(email="staff-pick-legacy@example.com", permissions=MANAGE)
    item, _blank_variant, _location, balance = _queued_with_stock(
        actor=actor, quantity=1, stock_quantity=1
    )
    old_session = PodPickSession.objects.create(
        code="PICK-LEGACY-01", created_by=actor, piece_count=1
    )
    old_line = PodPickSessionLine.objects.create(
        session=old_session,
        work_item=item,
        sequence=1,
        scan_identifier="POD-LEGACY-0001",
        shopify_order_number=item.shopify_order_number,
    )
    with pytest.raises(ValidationError):
        pick_sessions.open_session(
            actor=actor, source="test", work_item_public_ids=[str(item.public_id)]
        )
    page = client.get(reverse("portal:staff-pod-hub"))
    assert "Annuler ces étiquettes pour réimpression" in page.content.decode()
    assert "Anciennes étiquettes à reprendre" in page.content.decode()
    assert 'id="pod-pick-scan"' not in page.content.decode()
    response = client.post(
        reverse("portal:staff-pod-hub"),
        {
            "intent": "reissue_legacy_session",
            "session_public_id": str(old_session.public_id),
        },
    )
    assert response.status_code == 302
    old_line.refresh_from_db()
    assert old_line.voided_at is not None
    assert old_line.reservation_status == PodPickSessionLine.ReservationStatus.UNTRACKED
    balance.refresh_from_db()
    assert (balance.qty_on_hand, balance.qty_reserved) == (1, 0)
    assert not StockMovement.objects.filter(kind=StockMovement.Kind.PICK).exists()
    assert AuditLogEntry.objects.filter(action="pod.pick.legacy_session_reissued").exists()

    new_session = pick_sessions.open_session(
        actor=actor, source="test", work_item_public_ids=[str(item.public_id)]
    )
    assert new_session.lines.get().reservation_status == PodPickSessionLine.ReservationStatus.RESERVED
