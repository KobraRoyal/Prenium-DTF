from celery import shared_task

from apps.notifications.services.transactional import (
    send_file_correction_requested_email,
    send_order_created_email,
    send_order_priced_email,
    send_order_processing_email,
    send_order_ready_to_ship_email,
    send_order_shipped_email,
    send_payment_captured_email,
)
from apps.orders.models import Order
from apps.uploads.models import OrderUploadReview
from apps.uploads.services.reviews import OrderUploadReviewService


def _get_order(order_public_id: str) -> Order | None:
    return (
        Order.objects.filter(public_id=order_public_id)
        .select_related("customer", "created_by", "shipment")
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
    name="notifications.send_order_processing_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_order_processing_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_order_processing_email(order=order)


@shared_task(
    name="notifications.send_order_ready_to_ship_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_order_ready_to_ship_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_order_ready_to_ship_email(order=order)


@shared_task(
    name="notifications.send_order_shipped_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_order_shipped_email_task(order_public_id: str) -> None:
    if order := _get_order(order_public_id):
        send_order_shipped_email(order=order)


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


@shared_task(
    name="notifications.send_file_correction_requested_email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def send_file_correction_requested_email_task(review_public_id: str) -> None:
    review = (
        OrderUploadReview.objects.filter(public_id=review_public_id)
        .select_related(
            "order_upload",
            "order_upload__order",
            "order_upload__order__customer",
            "order_upload__order__created_by",
        )
        .first()
    )
    if review is None or review.status != OrderUploadReview.Status.CHANGES_REQUESTED:
        return
    if send_file_correction_requested_email(review=review):
        OrderUploadReviewService().mark_client_notified(review_public_id=review.public_id)
