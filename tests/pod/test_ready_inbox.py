import pytest
from apps.customers.models import Customer
from apps.notifications.models import WorkshopNotificationEvent
from apps.pod.models import PodQualityCheck, PodUnit
from apps.pod.services.ready_inbox import PodReadyInboxService
from django.core.exceptions import PermissionDenied

from tests.pod.test_ready_notification import _actor, _ready_order_fixture

pytestmark = pytest.mark.django_db


def test_ready_inbox_shows_current_production_only():
    actor = _actor()
    order, _item, units = _ready_order_fixture(unit_count=1)
    check = PodQualityCheck.objects.create(unit=units[0], result=PodQualityCheck.Result.PASS)
    event = WorkshopNotificationEvent.objects.create(
        event_type=WorkshopNotificationEvent.EventType.POD_ORDER_QC_READY,
        customer=order.customer,
        pod_order=order,
        pod_ready_check=check,
    )
    inbox = PodReadyInboxService()

    assert inbox.list_recent(actor=actor) == []

    units[0].status = PodUnit.Status.QC_PASSED
    units[0].save(update_fields=("status", "updated_at"))
    assert inbox.list_recent(actor=actor) == [event]

    units[0].status = PodUnit.Status.ISSUE
    units[0].save(update_fields=("status", "updated_at"))
    assert inbox.list_recent(actor=actor) == []


def test_ready_inbox_rejects_non_staff():
    with pytest.raises(PermissionDenied):
        PodReadyInboxService().list_recent(actor=None)


def test_ready_inbox_hides_cross_tenant_event():
    actor = _actor()
    order, _item, units = _ready_order_fixture(unit_count=1)
    units[0].status = PodUnit.Status.QC_PASSED
    units[0].save(update_fields=("status", "updated_at"))
    check = PodQualityCheck.objects.create(unit=units[0], result=PodQualityCheck.Result.PASS)
    WorkshopNotificationEvent.objects.create(
        event_type=WorkshopNotificationEvent.EventType.POD_ORDER_QC_READY,
        customer=Customer.objects.create(name="Other event tenant"),
        pod_order=order,
        pod_ready_check=check,
    )

    assert PodReadyInboxService().list_recent(actor=actor) == []
