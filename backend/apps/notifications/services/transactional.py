from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.notifications.models import EmailTemplate
from apps.notifications.services.email_templates import EmailTemplateService
from apps.orders.models import Order

logger = logging.getLogger(__name__)
email_template_service = EmailTemplateService()


def _recipient_emails_for_order(order: Order) -> list[str]:
    emails: list[str] = []
    created_by = getattr(order, "created_by", None)
    if created_by is not None and getattr(created_by, "email", ""):
        emails.append(created_by.email.strip())

    billing = (order.customer.billing_email or "").strip()
    if billing and billing.lower() not in {e.lower() for e in emails}:
        emails.append(billing)

    if not emails:
        from apps.customers.models import CustomerMembership

        m = (
            CustomerMembership.objects.filter(customer=order.customer, is_active=True)
            .select_related("user")
            .first()
        )
        if m is not None and getattr(m.user, "email", ""):
            emails.append(m.user.email.strip())

    return emails


def _internal_recipient_emails() -> list[str]:
    recipients = getattr(settings, "INTERNAL_NOTIFICATION_EMAILS", [])
    unique: list[str] = []
    seen: set[str] = set()
    for recipient in recipients:
        email = str(recipient).strip()
        normalized = email.lower()
        if email and normalized not in seen:
            seen.add(normalized)
            unique.append(email)
    return unique


def _send_event_email(
    *,
    event: str,
    order: Order,
    context_overrides: dict[str, str] | None = None,
) -> set[str]:
    sent_audiences: set[str] = set()
    audiences = (
        (EmailTemplate.Audience.CLIENT, _recipient_emails_for_order(order)),
        (EmailTemplate.Audience.INTERNAL, _internal_recipient_emails()),
    )
    for audience, recipients in audiences:
        if not recipients:
            logger.info(
                "Skipping %s/%s email: no recipient for order %s",
                event,
                audience,
                order.public_id,
            )
            continue
        rendered = email_template_service.render_for_order(
            event=event,
            audience=audience,
            order=order,
            context_overrides=context_overrides,
        )
        if rendered is None:
            logger.info(
                "Skipping %s/%s email: template disabled for order %s",
                event,
                audience,
                order.public_id,
            )
            continue
        subject, body = rendered
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
        sent_audiences.add(audience)
    return sent_audiences


def send_order_created_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    _send_event_email(event=EmailTemplate.Event.ORDER_CREATED, order=order)


def send_payment_captured_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    _send_event_email(event=EmailTemplate.Event.PAYMENT_CAPTURED, order=order)


def send_order_processing_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    _send_event_email(event=EmailTemplate.Event.ORDER_PROCESSING, order=order)


def send_order_ready_to_ship_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    _send_event_email(event=EmailTemplate.Event.ORDER_READY_TO_SHIP, order=order)


def send_order_shipped_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    shipment = getattr(order, "shipment", None)
    _send_event_email(
        event=EmailTemplate.Event.ORDER_SHIPPED,
        order=order,
        context_overrides={
            "shipment.tracking_number": getattr(shipment, "tracking_number", ""),
            "shipment.tracking_url": getattr(shipment, "tracking_url", ""),
            "shipment.status": (
                getattr(shipment, "sendcloud_status_message", "")
                or getattr(shipment, "sendcloud_status_code", "")
            ),
        },
    )


def schedule_order_created_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_order_created_email_task

    transaction.on_commit(lambda: send_order_created_email_task.delay(str(order_public_id)))


def schedule_payment_captured_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_payment_captured_email_task

    transaction.on_commit(lambda: send_payment_captured_email_task.delay(str(order_public_id)))


def schedule_order_processing_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_order_processing_email_task

    transaction.on_commit(lambda: send_order_processing_email_task.delay(str(order_public_id)))


def schedule_order_ready_to_ship_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_order_ready_to_ship_email_task

    transaction.on_commit(
        lambda: send_order_ready_to_ship_email_task.delay(str(order_public_id))
    )


def schedule_order_shipped_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_order_shipped_email_task

    transaction.on_commit(lambda: send_order_shipped_email_task.delay(str(order_public_id)))


def send_order_priced_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    if order.billing_mode != Order.BillingMode.DEFERRED:
        return
    _send_event_email(event=EmailTemplate.Event.ORDER_PRICED, order=order)


def schedule_order_priced_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_order_priced_email_task

    transaction.on_commit(lambda: send_order_priced_email_task.delay(str(order_public_id)))


def send_file_correction_requested_email(*, review) -> bool:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return False
    upload = review.order_upload
    sent_audiences = _send_event_email(
        event=EmailTemplate.Event.FILE_CORRECTION_REQUESTED,
        order=upload.order,
        context_overrides={
            "upload.filename": upload.original_filename,
            "review.reason": review.get_reason_code_display(),
            "review.comment": review.comment,
        },
    )
    return EmailTemplate.Audience.CLIENT in sent_audiences


def schedule_file_correction_requested_email(*, review_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_file_correction_requested_email_task

    transaction.on_commit(
        lambda: send_file_correction_requested_email_task.delay(str(review_public_id))
    )
