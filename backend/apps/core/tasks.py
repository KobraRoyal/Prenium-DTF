from celery import shared_task
from django.conf import settings

from apps.accounts.services.privacy import apply_privacy_retention


@shared_task(name="core.ping_task")
def ping_task() -> str:
    return "pong"


@shared_task(name="core.apply_privacy_retention")
def apply_privacy_retention_task() -> dict[str, int]:
    return apply_privacy_retention(
        audit_ip_days=int(getattr(settings, "PRIVACY_AUDIT_IP_RETENTION_DAYS", 365)),
        payment_payload_days=int(getattr(settings, "PRIVACY_PAYMENT_PAYLOAD_RETENTION_DAYS", 90)),
        shipment_snapshot_days=int(
            getattr(settings, "PRIVACY_SHIPMENT_SNAPSHOT_RETENTION_DAYS", 90)
        ),
        prospect_pii_days=int(getattr(settings, "PRIVACY_PROSPECT_PII_RETENTION_DAYS", 730)),
    )
