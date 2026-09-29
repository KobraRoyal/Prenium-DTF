from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.pod.models import PodQualityCheck, PodUnit
from apps.pod.services.pose import PodPoseService
from apps.pod.services.qc import PodQcService
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, connections

from tests.pod.test_pose import _prepared_unit
from tests.pod.test_shopify_ingest import _ingest
from tests.pod.test_variant_config import MANAGE, VIEW, staff_client

pytestmark = pytest.mark.django_db

qc = PodQcService()
pose = PodPoseService()


def _pressed_unit(tmp_path, settings, actor):
    unit = _prepared_unit(tmp_path, settings, actor)
    return pose.mark_pressed(actor=actor, scan_identifier=unit.scan_identifier, source="test")


def test_qc_pass_is_idempotent_and_audited(tmp_path, settings):
    actor, _client = staff_client(
        email="staff-qc-pass@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _pressed_unit(tmp_path, settings, actor)

    first = qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test")
    second = qc.decide(
        actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test"
    )

    assert first.status == second.status == PodUnit.Status.QC_PASSED
    assert (
        PodQualityCheck.objects.filter(unit=unit, result=PodQualityCheck.Result.PASS).count() == 1
    )
    assert (
        AuditLogEntry.objects.filter(
            action="pod.qc.passed", target_public_id=unit.public_id
        ).count()
        == 1
    )
    assert (
        qc.lookup(actor=actor, scan_identifier=unit.scan_identifier)["checks"][0].result == "pass"
    )


def test_qc_fail_requires_reason_then_explicit_reopen(tmp_path, settings):
    actor, _client = staff_client(
        email="staff-qc-fail@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _pressed_unit(tmp_path, settings, actor)
    with pytest.raises(ValidationError, match="motif"):
        qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=False, source="test")

    rejected = qc.decide(
        actor=actor,
        scan_identifier=unit.scan_identifier,
        passed=False,
        defect_code="Pose décalée",
        note="Repositionner le transfert",
        source="test",
    )
    assert rejected.status == PodUnit.Status.QC_FAILED
    with pytest.raises(ValidationError, match="Seule une pièce posée"):
        qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test")
    assert (
        qc.reopen(actor=actor, scan_identifier=unit.scan_identifier, source="test").status
        == PodUnit.Status.PRESSED
    )
    assert (
        qc.decide(
            actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test"
        ).status
        == PodUnit.Status.QC_PASSED
    )
    assert list(PodQualityCheck.objects.filter(unit=unit).values_list("result", flat=True)) == [
        "pass",
        "fail",
    ]
    assert AuditLogEntry.objects.filter(
        action="pod.qc.reopened", target_public_id=unit.public_id
    ).exists()


def test_qc_rejects_unpressed_and_issue_units(tmp_path, settings):
    actor, _client = staff_client(
        email="staff-qc-state@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _prepared_unit(tmp_path, settings, actor)
    with pytest.raises(ValidationError, match="Seule une pièce posée"):
        qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test")
    unit.status = PodUnit.Status.ISSUE
    unit.save(update_fields=["status", "updated_at"])
    with pytest.raises(ValidationError, match="Seule une pièce posée"):
        qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test")
    assert not PodQualityCheck.objects.filter(unit=unit).exists()


def test_qc_rejects_cross_customer_lot(tmp_path, settings):
    actor, _client = staff_client(
        email="staff-qc-owner@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _pressed_unit(tmp_path, settings, actor)
    other = Customer.objects.create(name="Autre propriétaire")
    unit.lot.customer = other
    unit.lot.save(update_fields=["customer", "updated_at"])

    with pytest.raises(ValidationError, match="incohérents"):
        qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test")
    assert not PodQualityCheck.objects.filter(unit=unit).exists()


def test_qc_view_only_cannot_decide_or_reopen(tmp_path, settings):
    manager, _client = staff_client(
        email="staff-qc-manager@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _pressed_unit(tmp_path, settings, manager)
    viewer, _client = staff_client(email="staff-qc-viewer@example.com", permissions=VIEW)
    assert qc.lookup(actor=viewer, scan_identifier=unit.scan_identifier)["unit"].pk == unit.pk
    with pytest.raises(PermissionDenied):
        qc.decide(actor=viewer, scan_identifier=unit.scan_identifier, passed=True, source="test")
    with pytest.raises(PermissionDenied):
        qc.reopen(actor=viewer, scan_identifier=unit.scan_identifier, source="test")


def test_shopify_cancellation_freezes_piece_even_after_qc_pass(tmp_path, settings):
    actor, _client = staff_client(
        email="staff-qc-cancel@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _pressed_unit(tmp_path, settings, actor)
    qc.decide(actor=actor, scan_identifier=unit.scan_identifier, passed=True, source="test")
    store = unit.work_item.store
    store.webhook_secret = "qc-cancel-secret"
    store.save(update_fields=["webhook_secret", "updated_at"])

    result = _ingest(
        store=store,
        secret="qc-cancel-secret",
        payload={"name": unit.work_item.shopify_order_number},
        webhook_id="evt-qc-cancel",
        topic="orders/cancelled",
    )

    assert result["frozen"] == 1
    unit.refresh_from_db()
    assert unit.status == PodUnit.Status.ISSUE
    assert PodQualityCheck.objects.filter(unit=unit, result="pass").count() == 1
    with pytest.raises(ValidationError, match="annulée"):
        qc.reopen(actor=actor, scan_identifier=unit.scan_identifier, source="test")


@pytest.mark.django_db(transaction=True)
def test_qc_parallel_double_scan_creates_one_check(tmp_path, settings):
    if connection.vendor != "postgresql":
        pytest.skip("Le verrou de ligne est validé sur PostgreSQL.")
    actor, _client = staff_client(
        email="staff-qc-parallel@example.com", permissions=MANAGE + ("manage_warehouse",)
    )
    unit = _pressed_unit(tmp_path, settings, actor)
    start = Barrier(2)

    def confirm():
        connections.close_all()
        thread_actor = get_user_model().objects.get(pk=actor.pk)
        start.wait(timeout=10)
        try:
            return qc.decide(
                actor=thread_actor,
                scan_identifier=unit.scan_identifier,
                passed=True,
                source="test_parallel",
            ).status
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _index: confirm(), range(2)))

    assert statuses == [PodUnit.Status.QC_PASSED, PodUnit.Status.QC_PASSED]
    assert PodQualityCheck.objects.filter(unit=unit, result="pass").count() == 1
