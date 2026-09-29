import pytest
from apps.notifications.models import WorkshopNotificationEvent
from apps.notifications.services.workshop_push import WorkshopNotificationService
from apps.pod.models import PodRipWorkItem, PodUnit
from apps.pod.services.qc import PodQcService
from apps.pod.services.ready_inbox import PodReadyInboxService

from tests.pod.test_ready_notification import _actor, _ready_order_fixture

pytestmark = pytest.mark.django_db


def test_new_pod_line_after_first_ready_creates_new_internal_signal():
    actor = _actor()
    order, first_item, units = _ready_order_fixture(unit_count=1)
    qc = PodQcService()

    qc.decide(actor=actor, scan_identifier=units[0].scan_identifier, passed=True)
    first_event = WorkshopNotificationEvent.objects.get(pod_order=order)

    second_item = PodRipWorkItem.objects.create(
        store=order.store,
        variant=first_item.variant,
        shopify_order_number=order.order_number,
        shopify_order=order,
        shopify_line_item_id="line-2",
        quantity=1,
        status=PodRipWorkItem.Status.INCLUDED,
    )
    second_unit = PodUnit.objects.create(
        lot=units[0].lot,
        work_item=second_item,
        variant=first_item.variant,
        sequence=1,
        scan_identifier="POD-READY-NEW-LINE",
        status=PodUnit.Status.PRESSED,
    )
    assert PodReadyInboxService().list_recent(actor=actor) == []

    qc.decide(actor=actor, scan_identifier=second_unit.scan_identifier, passed=True)

    events = list(WorkshopNotificationEvent.objects.filter(pod_order=order))
    assert len(events) == 2
    assert events[0].public_id != first_event.public_id
    assert events[0].pod_ready_check_id != first_event.pod_ready_check_id
    assert PodReadyInboxService().list_recent(actor=actor) == [events[0]]
    assert WorkshopNotificationService._event_is_current(events[0]) is True
    assert WorkshopNotificationService._event_is_current(first_event) is False
