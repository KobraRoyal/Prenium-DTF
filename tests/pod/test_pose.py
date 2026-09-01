from __future__ import annotations

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.pod.models import PodUnit
from apps.pod.services.pose import PodPoseService
from django.core.exceptions import ValidationError
from django.urls import reverse

from tests.pod.test_rip_lots import configure_pod, rip
from tests.pod.test_variant_config import MANAGE, VIEW, pod_fixture, staff_client

pytestmark = pytest.mark.django_db

pose = PodPoseService()


def _prepared_unit(tmp_path, settings, actor):
    settings.MEDIA_ROOT = tmp_path
    dtf, _blank, blank_variant, variant = pod_fixture(actor=actor)
    configure_pod(actor, dtf, blank_variant, variant)
    rip.enqueue(
        actor=actor,
        source="test",
        variant_public_id=variant.public_id,
        shopify_order_number="SO-POSE",
        quantity=1,
    )
    lot = rip.prepare_dtf_lot(actor=actor, source="test")
    return lot.units.get()


def test_pose_scan_and_confirm(tmp_path, settings):
    actor, client = staff_client(email="staff-pose@example.com", permissions=MANAGE)
    unit = _prepared_unit(tmp_path, settings, actor)
    page = client.get(reverse("portal:staff-pod-pose-dtf"), {"scan": unit.scan_identifier})
    assert page.status_code == 200
    assert unit.scan_identifier.encode() in page.content
    confirm = client.post(
        reverse("portal:staff-pod-pose-dtf"),
        {"intent": "press", "scan_identifier": unit.scan_identifier},
    )
    assert confirm.status_code == 302
    unit.refresh_from_db()
    assert unit.status == PodUnit.Status.PRESSED
    assert AuditLogEntry.objects.filter(action="pod.pose.pressed").exists()


def test_unknown_scan_is_rejected(tmp_path, settings):
    actor, _client = staff_client(email="staff-pose-miss@example.com", permissions=MANAGE)
    pod_fixture(actor=actor)
    with pytest.raises(ValidationError, match="introuvable"):
        pose.lookup(actor=actor, scan_identifier="POD-MISSING")


def test_view_only_cannot_confirm_pose(tmp_path, settings):
    manager, _client = staff_client(email="staff-pose-mgr@example.com", permissions=MANAGE)
    unit = _prepared_unit(tmp_path, settings, manager)
    _viewer, client = staff_client(email="staff-pose-ro@example.com", permissions=VIEW)
    response = client.post(
        reverse("portal:staff-pod-pose-dtf"),
        {"intent": "press", "scan_identifier": unit.scan_identifier},
    )
    assert response.status_code == 403
