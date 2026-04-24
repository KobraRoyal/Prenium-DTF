from typing import Any

from apps.auditlog.models import AuditLogEntry


def record_event(
    *,
    action: str,
    actor=None,
    target=None,
    status: str = AuditLogEntry.Status.SUCCESS,
    message: str = "",
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditLogEntry:
    target_model = ""
    target_public_id = None

    if target is not None:
        target_model = target.__class__.__name__
        target_public_id = getattr(target, "public_id", None)

    return AuditLogEntry.objects.create(
        actor=actor,
        action=action,
        target_model=target_model,
        target_public_id=target_public_id,
        status=status,
        message=message,
        ip_address=ip_address,
        metadata=metadata or {},
    )
