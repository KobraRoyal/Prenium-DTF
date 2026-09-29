import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.pod.services.pose import PodPoseService
from apps.pod.services.qc import PodQcService
from tests.pod.test_variant_config import staff_client

pytestmark = pytest.mark.django_db


def test_catalog_right_cannot_press_or_decide_quality():
    actor, _client = staff_client(
        email="pod-catalog-floor@example.com",
        permissions=("access_pod_atelier", "manage_pod_catalog"),
    )

    with pytest.raises(PermissionDenied):
        PodPoseService().mark_pressed(actor=actor, scan_identifier="POD-X", source="test")
    with pytest.raises(PermissionDenied):
        PodQcService().decide(
            actor=actor,
            scan_identifier="POD-X",
            passed=True,
            source="test",
        )


def test_production_right_passes_the_permission_gate():
    actor, _client = staff_client(
        email="pod-floor-operator@example.com",
        permissions=("access_pod_atelier", "operate_pod_production"),
    )

    with pytest.raises(ValidationError, match="Pièce introuvable"):
        PodPoseService().mark_pressed(actor=actor, scan_identifier="POD-X", source="test")
    with pytest.raises(ValidationError, match="Pièce introuvable"):
        PodQcService().decide(
            actor=actor,
            scan_identifier="POD-X",
            passed=True,
            source="test",
        )
