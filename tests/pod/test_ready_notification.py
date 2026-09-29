from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

import pytest
from apps.accounts.models import StaffMembership
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.notifications.models import WorkshopNotificationEvent
from apps.pod.models import (
    PodRipLot,
    PodRipWorkItem,
    PodShopifyOrder,
    PodUnit,
    PrintTechnique,
    ShopifyProduct,
    ShopifyStore,
    ShopifyVariant,
)
from apps.pod.services.qc import PodQcService, is_pod_order_qc_ready
from apps.pod.services.shopify_ingest import ShopifyFulfillmentIngestService
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import connection, connections, transaction
from django.test import TestCase, override_settings

pytestmark = pytest.mark.django_db


def _actor():
    actor = get_user_model().objects.create_user(
        email="pod-ready@example.com",
        password="pass",
        is_staff=True,
    )
    StaffMembership.objects.create(user=actor)
    actor.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        Permission.objects.get(codename="manage_pod_catalog"),
        Permission.objects.get(codename="operate_pod_production"),
        Permission.objects.get(codename="access_pod_atelier"),
    )
    return actor


def _ready_order_fixture(*, unit_count: int = 2):
    customer = Customer.objects.create(name="POD tenant")
    store = ShopifyStore.objects.create(
        customer=customer,
        slug="pod-ready-store",
        name="POD ready store",
        shop_domain="pod-ready-store.myshopify.com",
    )
    product = ShopifyProduct.objects.create(store=store, external_id="product", title="Product")
    variant = ShopifyVariant.objects.create(
        product=product,
        external_id="variant",
        title="Variant",
        sku="POD-READY",
    )
    order = PodShopifyOrder.objects.create(
        store=store,
        customer=customer,
        external_order_id="shopify-order-1",
        order_number="#POD-READY",
    )
    item = PodRipWorkItem.objects.create(
        store=store,
        variant=variant,
        shopify_order_number=order.order_number,
        shopify_order=order,
        shopify_line_item_id="line-1",
        quantity=unit_count,
        status=PodRipWorkItem.Status.INCLUDED,
    )
    technique = PrintTechnique.objects.create(code="dtf-ready", name="DTF ready")
    lot = PodRipLot.objects.create(
        code="LOT-POD-READY",
        customer=customer,
        technique=technique,
        nas_relative_path="pod/ready",
        file_count=1,
    )
    units = [
        PodUnit.objects.create(
            lot=lot,
            work_item=item,
            variant=variant,
            sequence=sequence,
            scan_identifier=f"POD-READY-{sequence}",
            status=PodUnit.Status.PRESSED,
        )
        for sequence in range(1, unit_count + 1)
    ]
    return order, item, units


@override_settings(WEB_PUSH_ENABLED=True)
def test_last_qc_pass_publishes_one_internal_pod_ready_event_after_commit():
    actor = _actor()
    order, _item, units = _ready_order_fixture()
    service = PodQcService()

    with patch(
        "apps.notifications.services.workshop_push.WorkshopNotificationService._schedule_fanout"
    ) as schedule:
        with TestCase.captureOnCommitCallbacks(execute=True):
            service.decide(
                actor=actor,
                scan_identifier=units[0].scan_identifier,
                passed=True,
                source="test",
            )
        assert not WorkshopNotificationEvent.objects.exists()
        with TestCase.captureOnCommitCallbacks(execute=True):
            service.decide(
                actor=actor,
                scan_identifier=units[1].scan_identifier,
                passed=True,
                source="test",
            )
        service.decide(
            actor=actor,
            scan_identifier=units[1].scan_identifier,
            passed=True,
            source="test",
        )

    event = WorkshopNotificationEvent.objects.get()
    assert event.event_type == WorkshopNotificationEvent.EventType.POD_ORDER_QC_READY
    assert event.pod_order_id == order.pk
    assert event.order_id is None
    assert event.customer_id == order.customer_id
    schedule.assert_called_once_with(str(event.public_id))
    assert (
        AuditLogEntry.objects.filter(
            action=WorkshopNotificationEvent.EventType.POD_ORDER_QC_READY,
            target_public_id=event.public_id,
        ).count()
        == 1
    )


def test_ready_predicate_blocks_incomplete_cancelled_and_cross_tenant_data():
    order, item, units = _ready_order_fixture(unit_count=1)
    units[0].status = PodUnit.Status.QC_PASSED
    units[0].save(update_fields=("status", "updated_at"))
    assert is_pod_order_qc_ready(order) is True

    item.status = PodRipWorkItem.Status.QUEUED
    item.save(update_fields=("status", "updated_at"))
    assert is_pod_order_qc_ready(order) is False

    item.status = PodRipWorkItem.Status.INCLUDED
    item.skip_reason = "Commande Shopify annulée — déjà en production."
    item.save(update_fields=("status", "skip_reason", "updated_at"))
    assert is_pod_order_qc_ready(order) is False

    item.skip_reason = ""
    item.save(update_fields=("skip_reason", "updated_at"))
    units[0].lot.customer = Customer.objects.create(name="Other tenant")
    units[0].lot.save(update_fields=("customer", "updated_at"))
    assert is_pod_order_qc_ready(order) is False


def test_ready_predicate_requires_exact_unit_quantity():
    order, _item, units = _ready_order_fixture(unit_count=2)
    units[0].status = PodUnit.Status.QC_PASSED
    units[0].save(update_fields=("status", "updated_at"))
    units[1].delete()

    assert is_pod_order_qc_ready(order) is False


@pytest.mark.django_db(transaction=True)
def test_parallel_last_scans_publish_exactly_one_ready_event():
    if connection.vendor != "postgresql":
        pytest.skip("Le verrou de commande est validé sur PostgreSQL.")
    actor = _actor()
    order, _item, units = _ready_order_fixture()
    start = Barrier(2)

    def confirm(unit_public_id):
        connections.close_all()
        thread_actor = get_user_model().objects.get(pk=actor.pk)
        unit = PodUnit.objects.get(public_id=unit_public_id)
        start.wait(timeout=10)
        try:
            return (
                PodQcService()
                .decide(
                    actor=thread_actor,
                    scan_identifier=unit.scan_identifier,
                    passed=True,
                    source="test_parallel",
                )
                .status
            )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(confirm, [unit.public_id for unit in units]))

    assert statuses == [PodUnit.Status.QC_PASSED, PodUnit.Status.QC_PASSED]
    assert (
        WorkshopNotificationEvent.objects.filter(
            event_type=WorkshopNotificationEvent.EventType.POD_ORDER_QC_READY,
            pod_order=order,
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_cancellation_holding_store_lock_blocks_last_qc_signal():
    if connection.vendor != "postgresql":
        pytest.skip("La sérialisation QC/annulation est validée sur PostgreSQL.")
    actor = _actor()
    order, _item, units = _ready_order_fixture(unit_count=1)
    cancellation_locked_store = Event()
    qc_attempting = Event()

    def cancel():
        connections.close_all()
        try:
            with transaction.atomic():
                store = ShopifyStore.objects.select_for_update(of=("self",)).get(pk=order.store_id)
                cancellation_locked_store.set()
                assert qc_attempting.wait(timeout=10)
                ShopifyFulfillmentIngestService()._cancel_order(
                    store=store,
                    order_number=order.order_number,
                    external_order_id=order.external_order_id,
                    shop_domain=store.shop_domain,
                )
        finally:
            connections.close_all()

    def confirm():
        connections.close_all()
        try:
            assert cancellation_locked_store.wait(timeout=10)
            qc_attempting.set()
            thread_actor = get_user_model().objects.get(pk=actor.pk)
            with pytest.raises(ValidationError, match="annulée"):
                PodQcService().decide(
                    actor=thread_actor,
                    scan_identifier=units[0].scan_identifier,
                    passed=True,
                    source="test_parallel_cancel",
                )
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_cancel = pool.submit(cancel)
        future_qc = pool.submit(confirm)
        future_cancel.result(timeout=15)
        future_qc.result(timeout=15)

    assert not WorkshopNotificationEvent.objects.filter(pod_order=order).exists()
    units[0].refresh_from_db()
    assert units[0].status == PodUnit.Status.ISSUE
