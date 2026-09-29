from __future__ import annotations

from apps.notifications.models import WorkshopNotificationEvent
from apps.pod.services.qc import is_pod_order_qc_ready
from apps.pod.services.validation import require_staff_perm


class PodReadyInboxService:
    """Read current POD production-ready signals for the internal workshop."""

    def list_recent(self, *, actor, limit: int = 8) -> list[WorkshopNotificationEvent]:
        require_staff_perm(
            actor,
            "pod.access_pod_atelier",
            source="pod.ready_inbox",
            action="pod.ready_inbox.permission_rejected",
        )
        safe_limit = min(max(int(limit), 1), 20)
        candidates = (
            WorkshopNotificationEvent.objects.filter(
                event_type=WorkshopNotificationEvent.EventType.POD_ORDER_QC_READY,
                pod_order__isnull=False,
            )
            .select_related("pod_order", "pod_order__store")
            .order_by("-created_at", "-id")[: safe_limit * 5]
        )
        visible = []
        seen_order_ids = set()
        for event in candidates:
            if (
                event.pod_order_id in seen_order_ids
                or event.customer_id != event.pod_order.customer_id
                or not is_pod_order_qc_ready(event.pod_order)
            ):
                continue
            visible.append(event)
            seen_order_ids.add(event.pod_order_id)
            if len(visible) == safe_limit:
                break
        return visible
