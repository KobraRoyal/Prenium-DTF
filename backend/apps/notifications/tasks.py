from celery import shared_task

from apps.notifications.services.transactional import (
    send_b2b_order_submitted_email,
    send_order_created_email,
    send_order_priced_email,
    send_payment_captured_email,
)
from apps.orders.models import Order


def _get_order(order_public_id: str) -> Order | None:
    return (
        Order.objects.filter(public_id=order_public_id)
        .select_related("customer", "created_by")
        .first()
    )


@shared_task(
    name="notifications.send_order_created_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_order_created_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_order_created_email(order=order)


@shared_task(
    name="notifications.send_payment_captured_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_payment_captured_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_payment_captured_email(order=order)


@shared_task(
    name="notifications.send_b2b_order_submitted_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_b2b_order_submitted_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_b2b_order_submitted_email(order=order)


@shared_task(
    name="notifications.send_order_priced_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_order_priced_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_order_priced_email(order=order)
