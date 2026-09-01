from __future__ import annotations

import pytest
from apps.inventory.models import StockBalance, StockMovement, WarehouseZone
from apps.inventory.services import StockOpsService, WarehouseLayoutService
from apps.pod.services import BlankCatalogService
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.pod.test_catalog_and_warehouse import MANAGE, VIEW, staff_client
from tests.pod.test_variant_config import pod_fixture

pytestmark = pytest.mark.django_db

stock = StockOpsService()
warehouse = WarehouseLayoutService()
blanks = BlankCatalogService()


def _bin(actor, *, zone_kind, code):
    warehouse.ensure_default_layout(actor=actor)
    zone = WarehouseZone.objects.get(kind=zone_kind, warehouse__code="atl-01")
    return warehouse.create_location(
        actor=actor,
        source="test",
        data={"zone_public_id": str(zone.public_id), "code": code, "label": code},
    )


def test_receive_pick_putaway_and_pod_18(tmp_path, settings):
    actor, client = staff_client(email="staff-wms@example.com", permissions=MANAGE)
    _dtf, _blank, blank_variant, _variant = pod_fixture(actor=actor)
    blanks_bin = _bin(actor, zone_kind=WarehouseZone.Kind.BLANKS, code="A-01-01-A")
    returns_bin = _bin(actor, zone_kind=WarehouseZone.Kind.RETURNS, code="R-01-01-A")
    stock.receive_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        location_public_id=blanks_bin.public_id,
        quantity=2,
    )
    with pytest.raises(ValidationError, match="POD-17"):
        stock.pick_blank(
            actor=actor,
            source="test",
            blank_variant_public_id=blank_variant.public_id,
            scanned_bin_code="",
            quantity=1,
        )
    stock.pick_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        scanned_bin_code="a-01-01-a",
        quantity=2,
    )
    with pytest.raises(ValidationError, match="POD-18"):
        stock.pick_blank(
            actor=actor,
            source="test",
            blank_variant_public_id=blank_variant.public_id,
            scanned_bin_code="A-01-01-A",
            quantity=1,
        )
    stock.putaway_return(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        location_public_id=returns_bin.public_id,
        quantity=1,
    )
    assert StockMovement.objects.filter(kind=StockMovement.Kind.RECEIPT).exists()
    assert StockBalance.objects.get(location=returns_bin).qty_on_hand == 1
    page = client.get(reverse("portal:staff-pod-stock"))
    assert page.status_code == 200
    assert b"Picking" in page.content


def test_customer_stock_is_isolated_from_atelier_pick():
    from apps.customers.models import Customer

    actor, _client = staff_client(email="staff-wms-client@example.com", permissions=MANAGE)
    _dtf, _blank, blank_variant, _variant = pod_fixture(actor=actor)
    client_bin = _bin(actor, zone_kind=WarehouseZone.Kind.CLIENT, code="C-01-01-A")
    customer = Customer.objects.create(name="Owner Client Stock")
    stock.receive_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        location_public_id=client_bin.public_id,
        quantity=2,
        owner_kind="customer",
        customer_public_id=customer.public_id,
    )
    with pytest.raises(ValidationError, match="POD-18"):
        stock.pick_blank(
            actor=actor,
            source="test",
            blank_variant_public_id=blank_variant.public_id,
            scanned_bin_code="C-01-01-A",
            quantity=1,
            owner_kind="atelier",
        )
    stock.pick_blank(
        actor=actor,
        source="test",
        blank_variant_public_id=blank_variant.public_id,
        scanned_bin_code="C-01-01-A",
        quantity=1,
        owner_kind="customer",
        customer_public_id=customer.public_id,
    )


def test_finished_sku_receive_and_pick():
    actor, _client = staff_client(email="staff-wms-fin@example.com", permissions=MANAGE)
    pod_fixture(actor=actor)
    finished_bin = _bin(actor, zone_kind=WarehouseZone.Kind.FINISHED, code="F-01-01-A")
    stock.receive_finished(
        actor=actor,
        source="test",
        finished_sku="tee-wht-m-fin",
        location_public_id=finished_bin.public_id,
        quantity=2,
    )
    stock.pick_finished(
        actor=actor,
        source="test",
        finished_sku="TEE-WHT-M-FIN",
        scanned_bin_code="F-01-01-A",
        quantity=1,
    )
    assert StockBalance.objects.get(finished_sku="TEE-WHT-M-FIN").qty_on_hand == 1


def test_view_only_cannot_receive():
    actor, client = staff_client(email="staff-wms-ro@example.com", permissions=VIEW)
    response = client.post(
        reverse("portal:staff-pod-stock"),
        {"intent": "receive", "quantity": "1"},
    )
    assert response.status_code == 403
