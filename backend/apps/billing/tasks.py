from celery import shared_task

from apps.billing.services.payments import PaymentService


@shared_task(name="billing.recover_incomplete_captures")
def recover_incomplete_captures_task() -> dict[str, int]:
    return PaymentService().recover_incomplete_captures(limit=100)


@shared_task(name="billing.reconcile_active_payments")
def reconcile_active_payments_task() -> dict[str, int]:
    return PaymentService().reconcile_active_payments(limit=100)
