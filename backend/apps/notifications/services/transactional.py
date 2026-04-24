from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from apps.orders.models import Order

logger = logging.getLogger(__name__)


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


def send_order_created_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    recipients = _recipient_emails_for_order(order)
    if not recipients:
        logger.info("Skipping order_created email: no recipient for order %s", order.public_id)
        return
    context = {"order": order}
    subject = render_to_string("notifications/email/order_created_subject.txt", context).strip()
    body = render_to_string("notifications/email/order_created_body.txt", context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Transactional email failed (order_created) order_public_id=%s",
            order.public_id,
        )


def send_payment_captured_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    recipients = _recipient_emails_for_order(order)
    if not recipients:
        logger.info(
            "Skipping payment_captured email: no recipient for order %s",
            order.public_id,
        )
        return
    context = {"order": order}
    subject = render_to_string("notifications/email/payment_captured_subject.txt", context).strip()
    body = render_to_string("notifications/email/payment_captured_body.txt", context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Transactional email failed (payment_captured) order_public_id=%s",
            order.public_id,
        )


def send_b2b_order_submitted_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    recipients = _recipient_emails_for_order(order)
    if not recipients:
        logger.info(
            "Skipping b2b_order_submitted email: no recipient for order %s",
            order.public_id,
        )
        return
    context = {"order": order}
    subject = render_to_string(
        "notifications/email/b2b_order_submitted_subject.txt",
        context,
    ).strip()
    body = render_to_string("notifications/email/b2b_order_submitted_body.txt", context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Transactional email failed (b2b_order_submitted) order_public_id=%s",
            order.public_id,
        )


def schedule_order_created_email(*, order_public_id) -> None:
    from django.db import transaction

    def _send() -> None:
        order = (
            Order.objects.filter(public_id=order_public_id)
            .select_related("customer", "created_by")
            .first()
        )
        if order is not None:
            send_order_created_email(order=order)

    transaction.on_commit(_send)


def schedule_payment_captured_email(*, order_public_id) -> None:
    from django.db import transaction

    def _send() -> None:
        order = (
            Order.objects.filter(public_id=order_public_id)
            .select_related("customer", "created_by")
            .first()
        )
        if order is not None:
            send_payment_captured_email(order=order)

    transaction.on_commit(_send)


def schedule_b2b_order_submitted_email(*, order_public_id) -> None:
    from django.db import transaction

    def _send() -> None:
        order = (
            Order.objects.filter(public_id=order_public_id)
            .select_related("customer", "created_by")
            .first()
        )
        if order is not None:
            send_b2b_order_submitted_email(order=order)

    transaction.on_commit(_send)


def send_order_priced_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    if order.billing_mode != Order.BillingMode.DEFERRED:
        return
    recipients = _recipient_emails_for_order(order)
    if not recipients:
        logger.info("Skipping order_priced email: no recipient for order %s", order.public_id)
        return
    context = {"order": order}
    subject = render_to_string("notifications/email/order_priced_subject.txt", context).strip()
    body = render_to_string("notifications/email/order_priced_body.txt", context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Transactional email failed (order_priced) order_public_id=%s",
            order.public_id,
        )


def schedule_order_priced_email(*, order_public_id) -> None:
    from django.db import transaction

    def _send() -> None:
        order = (
            Order.objects.filter(public_id=order_public_id)
            .select_related("customer", "created_by")
            .first()
        )
        if order is not None:
            send_order_priced_email(order=order)

    transaction.on_commit(_send)
