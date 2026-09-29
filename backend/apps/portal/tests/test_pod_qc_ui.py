from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import StaffMembership

pytestmark = pytest.mark.django_db


def _staff_client(*, email: str, permissions: tuple[str, ...]):
    user = get_user_model().objects.create_user(email=email, password="pass", is_staff=True)
    user.user_permissions.add(
        Permission.objects.get(codename="access_staff_portal"),
        *(Permission.objects.get(codename=codename) for codename in permissions),
    )
    client = Client()
    assert client.login(email=email, password="pass")
    return user, client


def _unit(status="pressed"):
    return SimpleNamespace(
        status=status,
        scan_identifier="POD-QC-001",
        get_status_display=lambda: {
            "pressed": "Posé",
            "qc_passed": "QC validé",
            "qc_failed": "QC refusé",
        }[status],
        work_item=SimpleNamespace(
            shopify_order_number="SO-QC",
            store=SimpleNamespace(name="Boutique Test"),
        ),
        variant=SimpleNamespace(sku="TEE-NOIR-M", title="Tee-shirt noir M"),
    )


def _lookup(status="pressed", *, checks=None):
    return {"unit": _unit(status), "checks": checks or []}


def test_qc_requires_atelier_permission():
    _user, client = _staff_client(email="qc-denied@example.com", permissions=())

    assert client.get(reverse("portal:staff-pod-qc")).status_code == 403


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_view_only_can_scan_but_sees_no_mutation(qc_service):
    _user, client = _staff_client(
        email="qc-viewer@example.com", permissions=("access_pod_atelier",)
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup()

    response = client.get(reverse("portal:staff-pod-qc"), {"scan": "POD-QC-001"})

    assert response.status_code == 200
    body = response.content.decode()
    assert "Boutique Test" in body
    assert "Consultation seule" in body
    assert "Valider le QC" not in body
    assert "Refuser la pièce" not in body


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_view_only_mutation_permission_error_propagates(qc_service):
    _user, client = _staff_client(
        email="qc-viewer-post@example.com", permissions=("access_pod_atelier",)
    )
    qc_service.decide.side_effect = PermissionDenied

    response = client.post(
        reverse("portal:staff-pod-qc"),
        {
            "intent": "decide",
            "decision": "pass",
            "scan_identifier": "POD-QC-001",
        },
    )

    assert response.status_code == 403


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_catalog_right_does_not_open_the_decision(qc_service):
    _user, client = _staff_client(
        email="qc-catalog-only@example.com",
        permissions=("access_pod_atelier", "manage_pod_catalog"),
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup()

    response = client.get(reverse("portal:staff-pod-qc"), {"scan": "POD-QC-001"})

    body = response.content.decode()
    assert response.status_code == 200
    assert "Consultation seule" in body
    assert "Valider le QC" not in body
    assert "Refuser la pièce" not in body


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_manager_can_validate_and_refuse(qc_service):
    _user, client = _staff_client(
        email="qc-manager@example.com",
        permissions=("access_pod_atelier", "operate_pod_production"),
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup()
    qc_service.decide.return_value = _unit("qc_passed")

    page = client.get(reverse("portal:staff-pod-qc"), {"scan": "POD-QC-001"})
    body = page.content.decode()
    assert "Valider le QC" in body
    assert "Refuser la pièce" in body
    assert "Motif du refus" in body
    assert 'aria-current="page"' in body
    assert "csrfmiddlewaretoken" in body

    response = client.post(
        reverse("portal:staff-pod-qc"),
        {
            "intent": "decide",
            "decision": "pass",
            "scan_identifier": "POD-QC-001",
            "note": "RAS",
        },
    )
    assert response.status_code == 302
    qc_service.decide.assert_called_once_with(
        actor=page.wsgi_request.user,
        scan_identifier="POD-QC-001",
        passed=True,
        defect_code="",
        note="RAS",
        source="staff_pod",
    )


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_validation_error_is_inline_and_keeps_values(qc_service):
    _user, client = _staff_client(
        email="qc-error@example.com",
        permissions=("access_pod_atelier", "operate_pod_production"),
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup()
    qc_service.decide.side_effect = ValidationError("Le motif du refus est obligatoire.")

    response = client.post(
        reverse("portal:staff-pod-qc"),
        {
            "intent": "decide",
            "decision": "fail",
            "scan_identifier": "POD-QC-001",
            "note": "Revoir le col",
        },
    )

    assert response.status_code == 400
    body = response.content.decode()
    assert "Le motif du refus est obligatoire." in body
    assert "Revoir le col" in body
    assert 'aria-invalid="true"' in body


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_unknown_decision_never_falls_back_to_rejection(qc_service):
    _user, client = _staff_client(
        email="qc-unknown@example.com",
        permissions=("access_pod_atelier", "operate_pod_production"),
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup()

    response = client.post(
        reverse("portal:staff-pod-qc"),
        {
            "intent": "decide",
            "decision": "unexpected",
            "scan_identifier": "POD-QC-001",
        },
    )

    assert response.status_code == 400
    assert "Décision de contrôle qualité inconnue." in response.content.decode()
    qc_service.decide.assert_not_called()


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_recorded_refusal_is_a_warning(qc_service):
    _user, client = _staff_client(
        email="qc-refusal-tone@example.com", permissions=("access_pod_atelier",)
    )
    qc_service.list_pending.return_value = []

    response = client.get(reverse("portal:staff-pod-qc"), {"outcome": "failed"})

    body = response.content.decode()
    assert response.status_code == 200
    assert 'class="alert alert--warning" role="status">Refus enregistré.' in body
    assert "alert--success" not in body.split("Refus enregistré", 1)[0][-80:]


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_renders_decision_history(qc_service):
    _user, client = _staff_client(
        email="qc-history@example.com", permissions=("access_pod_atelier",)
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup(
        "qc_failed",
        checks=[
            SimpleNamespace(
                result="fail",
                defect_code="Décalage col",
                note="Repositionner le transfert",
                checked_by="Opérateur QC",
                created_at=None,
                get_result_display=lambda: "Refusé",
            )
        ],
    )

    response = client.get(reverse("portal:staff-pod-qc"), {"scan": "POD-QC-001"})

    body = response.content.decode()
    assert response.status_code == 200
    assert "Historique qualité" in body
    assert "Refusé" in body
    assert "Décalage col" in body
    assert "Repositionner le transfert" in body
    assert "Opérateur QC" in body


@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_reopen_is_explicit_and_permission_errors_propagate(qc_service):
    _user, client = _staff_client(
        email="qc-reopen@example.com",
        permissions=("access_pod_atelier", "operate_pod_production"),
    )
    qc_service.list_pending.return_value = []
    qc_service.lookup.return_value = _lookup("qc_failed")
    qc_service.reopen.side_effect = PermissionDenied

    page = client.get(reverse("portal:staff-pod-qc"), {"scan": "POD-QC-001"})
    assert "Reprendre après correction" in page.content.decode()

    response = client.post(
        reverse("portal:staff-pod-qc"),
        {"intent": "reopen", "scan_identifier": "POD-QC-001"},
    )
    assert response.status_code == 403


@patch("apps.portal.views_staff_pod_qc.ready_inbox_service")
@patch("apps.portal.views_staff_pod_qc.qc_service")
def test_qc_shows_internal_ready_signal_without_shipping_action(qc_service, ready_inbox):
    _user, client = _staff_client(
        email="qc-ready-viewer@example.com", permissions=("access_pod_atelier",)
    )
    qc_service.list_pending.return_value = []
    ready_inbox.list_recent.return_value = [
        SimpleNamespace(
            pod_order=SimpleNamespace(
                order_number="#POD-READY",
                store=SimpleNamespace(name="Boutique Atelier"),
            ),
            created_at=timezone.now(),
        )
    ]

    response = client.get(reverse("portal:staff-pod-qc"))

    assert response.status_code == 200
    body = response.content.decode()
    assert "Production POD terminée" in body
    assert "#POD-READY" in body
    assert "Boutique Atelier" in body
    assert "QC complet" in body
    assert "Shopify et Sendcloud" in body
    assert "Activer les alertes" in body
    assert "Créer une expédition" not in body


def test_push_polling_requires_pod_or_native_workshop_permission():
    denied_user, denied_client = _staff_client(email="qc-push-denied@example.com", permissions=())
    StaffMembership.objects.create(user=denied_user)
    assert denied_client.get(reverse("portal:staff-push-notification-events")).status_code == 403

    pod_user, pod_client = _staff_client(
        email="qc-push-pod@example.com", permissions=("access_pod_atelier",)
    )
    StaffMembership.objects.create(user=pod_user)
    response = pod_client.get(reverse("portal:staff-push-notification-events"))
    assert response.status_code == 200
    assert response.json()["events"] == []
