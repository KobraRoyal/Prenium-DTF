from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.urls import reverse
from django.utils import formats, timezone

from apps.auditlog.services import record_event
from apps.notifications.models import EmailTemplate, VolumeDiscountTierNotification
from apps.notifications.services.email_templates import EmailTemplateService
from apps.orders.models import Order

logger = logging.getLogger(__name__)
email_template_service = EmailTemplateService()

_NON_EXTERNAL_EMAIL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend",
    "django.core.mail.backends.dummy.EmailBackend",
    "django.core.mail.backends.filebased.EmailBackend",
    "django.core.mail.backends.locmem.EmailBackend",
}
_RESERVED_EMAIL_DOMAINS = {"example.com", "example.net", "example.org", "localhost"}
_RESERVED_EMAIL_SUFFIXES = (".invalid", ".localhost", ".test")


def _external_safe_recipients(
    recipients: list[str],
    *,
    event: str,
    audience: str,
) -> list[str]:
    """Block reserved QA addresses before an external email transport is used."""
    email_backend = str(getattr(settings, "EMAIL_BACKEND", ""))
    if email_backend in _NON_EXTERNAL_EMAIL_BACKENDS:
        return recipients

    safe_recipients: list[str] = []
    blocked_recipient = False
    for recipient in recipients:
        domain = recipient.strip().lower().rpartition("@")[2]
        if domain in _RESERVED_EMAIL_DOMAINS or domain.endswith(_RESERVED_EMAIL_SUFFIXES):
            blocked_recipient = True
            continue
        safe_recipients.append(recipient)

    if blocked_recipient:
        logger.warning("Blocked reserved QA recipient(s) before external email delivery.")
    return safe_recipients


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


def _recipient_emails_for_customer(customer) -> list[str]:
    emails: list[str] = []
    seen: set[str] = set()

    billing = (customer.billing_email or "").strip()
    if billing:
        emails.append(billing)
        seen.add(billing.lower())

    from apps.customers.models import CustomerMembership

    memberships = (
        CustomerMembership.objects.active()
        .filter(
            customer=customer,
            role__in=(CustomerMembership.Role.OWNER, CustomerMembership.Role.ADMIN),
        )
        .select_related("user")
        .order_by("role", "created_at")
    )
    for membership in memberships:
        email = (membership.user.email or "").strip()
        if email and email.lower() not in seen:
            emails.append(email)
            seen.add(email.lower())
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
        recipients = _external_safe_recipients(
            recipients,
            event=event,
            audience=audience,
        )
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


def _absolute_url(path: str) -> str:
    base_url = str(getattr(settings, "PUBLIC_BASE_URL", "http://localhost:8080")).rstrip("/")
    return f"{base_url}{path}"


def _prospect_context(profile) -> dict[str, str]:
    return {
        "site.name": "Prenium DTF",
        "prospect.first_name": profile.first_name,
        "prospect.last_name": profile.last_name,
        "prospect.company": profile.company,
        "prospect.email": profile.email,
        "prospect.country": profile.country,
        "prospect.siren": profile.siren,
        "prospect.vat_number": profile.vat_number,
        "customer.name": getattr(profile.customer, "name", "") if profile.customer_id else "",
    }


def _send_context_email(
    *,
    event: str,
    audience: str,
    recipients: list[str],
    context: dict[str, str],
) -> bool:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return False
    recipients = _external_safe_recipients(
        recipients,
        event=event,
        audience=audience,
    )
    if not recipients:
        return False
    rendered = email_template_service.render_for_context(
        event=event,
        audience=audience,
        context=context,
    )
    if rendered is None:
        return False
    subject, body = rendered
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=False)
    return True


def send_access_request_verification_email(*, profile) -> None:
    from apps.prospects.services.onboarding import make_email_verification_token

    context = _prospect_context(profile)
    token = make_email_verification_token(profile)
    context["action.url"] = _absolute_url(
        reverse("prospects:verify-email", kwargs={"token": token})
    )
    _send_context_email(
        event=EmailTemplate.Event.ACCESS_REQUEST_EMAIL_VERIFICATION,
        audience=EmailTemplate.Audience.CLIENT,
        recipients=[profile.email],
        context=context,
    )


def send_access_request_submitted_internal_email(*, profile) -> None:
    context = _prospect_context(profile)
    context["action.url"] = _absolute_url(
        reverse(
            "portal:staff-access-request-detail",
            kwargs={"profile_public_id": profile.public_id},
        )
    )
    _send_context_email(
        event=EmailTemplate.Event.ACCESS_REQUEST_SUBMITTED_INTERNAL,
        audience=EmailTemplate.Audience.INTERNAL,
        recipients=_internal_recipient_emails(),
        context=context,
    )


def send_access_request_approved_email(*, invitation) -> None:
    from apps.customers.services.invitations import make_invitation_token

    profile = invitation.customer.prospect_profiles.select_related("customer").get()
    context = _prospect_context(profile)
    context["action.url"] = _absolute_url(
        reverse(
            "portal:customer-invitation-accept",
            kwargs={"token": make_invitation_token(invitation)},
        )
    )
    _send_context_email(
        event=EmailTemplate.Event.ACCESS_REQUEST_APPROVED,
        audience=EmailTemplate.Audience.CLIENT,
        recipients=[invitation.email],
        context=context,
    )


def send_access_request_rejected_email(*, profile) -> None:
    context = _prospect_context(profile)
    context["review.reason"] = profile.rejection_reason
    _send_context_email(
        event=EmailTemplate.Event.ACCESS_REQUEST_REJECTED,
        audience=EmailTemplate.Audience.CLIENT,
        recipients=[profile.email],
        context=context,
    )


def _invitation_context(invitation) -> dict[str, str]:
    from apps.customers.services.invitations import make_invitation_token

    return {
        "site.name": "Prenium DTF",
        "customer.name": invitation.customer.name,
        "invitation.role": invitation.get_role_display(),
        "action.url": _absolute_url(
            reverse(
                "portal:customer-invitation-accept",
                kwargs={"token": make_invitation_token(invitation)},
            )
        ),
    }


def send_customer_invitation_email(*, invitation) -> None:
    _send_context_email(
        event=EmailTemplate.Event.CUSTOMER_MEMBER_INVITED,
        audience=EmailTemplate.Audience.CLIENT,
        recipients=[invitation.email],
        context=_invitation_context(invitation),
    )


def send_account_activated_email(*, invitation) -> None:
    context = _invitation_context(invitation)
    context["action.url"] = _absolute_url(reverse("portal:login"))
    _send_context_email(
        event=EmailTemplate.Event.ACCOUNT_ACTIVATED,
        audience=EmailTemplate.Audience.CLIENT,
        recipients=[invitation.email],
        context=context,
    )


def schedule_access_request_verification_email(*, profile_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_access_request_verification_email_task

    transaction.on_commit(
        lambda: send_access_request_verification_email_task.delay(str(profile_public_id))
    )


def schedule_access_request_submitted_internal_email(*, profile_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_access_request_submitted_internal_email_task

    transaction.on_commit(
        lambda: send_access_request_submitted_internal_email_task.delay(str(profile_public_id))
    )


def schedule_access_request_approved_email(*, invitation_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_access_request_approved_email_task

    transaction.on_commit(
        lambda: send_access_request_approved_email_task.delay(str(invitation_public_id))
    )


def schedule_access_request_rejected_email(*, profile_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_access_request_rejected_email_task

    transaction.on_commit(
        lambda: send_access_request_rejected_email_task.delay(str(profile_public_id))
    )


def schedule_customer_invitation_email(*, invitation_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_customer_invitation_email_task

    transaction.on_commit(
        lambda: send_customer_invitation_email_task.delay(str(invitation_public_id))
    )


def schedule_account_activated_email(*, invitation_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_account_activated_email_task

    transaction.on_commit(
        lambda: send_account_activated_email_task.delay(str(invitation_public_id))
    )


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

    transaction.on_commit(lambda: send_order_ready_to_ship_email_task.delay(str(order_public_id)))


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


def _client_order_billing_url(order: Order) -> str:
    return _absolute_url(
        reverse(
            "portal:client-order-panel-billing",
            kwargs={
                "customer_public_id": order.customer.public_id,
                "order_public_id": order.public_id,
            },
        )
    )


def send_order_awaiting_payment_email(*, order: Order) -> None:
    if not getattr(settings, "TRANSACTIONAL_EMAILS_ENABLED", True):
        return
    if order.billing_mode != Order.BillingMode.IMMEDIATE:
        return
    if order.pricing_status != Order.PricingStatus.PRICED:
        return
    if order.total_amount is None or order.total_amount <= 0:
        return
    _send_event_email(
        event=EmailTemplate.Event.ORDER_AWAITING_PAYMENT,
        order=order,
        context_overrides={"action.url": _client_order_billing_url(order)},
    )


def schedule_order_awaiting_payment_email(*, order_public_id) -> None:
    from django.db import transaction

    from apps.notifications.tasks import send_order_awaiting_payment_email_task

    transaction.on_commit(
        lambda: send_order_awaiting_payment_email_task.delay(str(order_public_id))
    )


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


def _format_decimal(value, places: int) -> str:
    return f"{value:.{places}f}".replace(".", ",")


def send_volume_discount_tier_reached_email(*, notification) -> bool:
    context = {
        "site.name": "Prenium DTF",
        "customer.name": notification.customer.name,
        "customer.billing_email": notification.customer.billing_email or "",
        "volume.month": formats.date_format(notification.month, "F Y"),
        "volume.monthly_linear_m": _format_decimal(
            notification.monthly_volume_linear_m,
            4,
        ),
        "volume.threshold_linear_m": _format_decimal(
            notification.threshold_linear_m,
            4,
        ),
        "volume.discount_percent": _format_decimal(notification.discount_percent, 2),
        "volume.discount_amount": _format_decimal(notification.discount_amount, 2),
        "action.url": _absolute_url(reverse("portal:client-dashboard")),
    }
    sent = False
    for recipient in _recipient_emails_for_customer(notification.customer):
        delivered = _send_context_email(
            event=EmailTemplate.Event.VOLUME_DISCOUNT_TIER_REACHED,
            audience=EmailTemplate.Audience.CLIENT,
            recipients=[recipient],
            context=context,
        )
        sent = delivered or sent
    return sent


@transaction.atomic
def schedule_volume_discount_tier_reached_email(
    *,
    customer,
    month,
    threshold_linear_m,
    monthly_volume_linear_m,
    discount_percent,
    discount_amount,
    actor,
    source: str,
) -> tuple[VolumeDiscountTierNotification, bool]:
    from apps.customers.models import Customer

    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    notification, created = VolumeDiscountTierNotification.objects.get_or_create(
        customer=customer,
        month=month,
        threshold_linear_m=threshold_linear_m,
        defaults={
            "monthly_volume_linear_m": monthly_volume_linear_m,
            "discount_percent": discount_percent,
            "discount_amount": discount_amount,
        },
    )
    if not created:
        return notification, False

    record_event(
        action="customer.volume_discount_tier_notification_scheduled",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        target=notification,
        metadata={
            "customer_public_id": str(customer.public_id),
            "month": month.isoformat(),
            "threshold_linear_m": f"{threshold_linear_m:.4f}",
            "discount_percent": f"{discount_percent:.2f}",
            "source": source,
        },
    )
    from apps.notifications.tasks import send_volume_discount_tier_reached_email_task

    transaction.on_commit(
        lambda: send_volume_discount_tier_reached_email_task.delay(str(notification.public_id))
    )
    return notification, True


@transaction.atomic
def _claim_volume_discount_tier_notification(*, notification_public_id):
    notification = (
        VolumeDiscountTierNotification.objects.select_for_update()
        .select_related("customer")
        .filter(public_id=notification_public_id)
        .first()
    )
    if notification is None or notification.status != VolumeDiscountTierNotification.Status.PENDING:
        return None
    notification.status = VolumeDiscountTierNotification.Status.SENDING
    notification.delivery_started_at = timezone.now()
    notification.attempt_count += 1
    notification.save(
        update_fields=[
            "status",
            "delivery_started_at",
            "attempt_count",
            "updated_at",
        ]
    )
    return notification


@transaction.atomic
def _finalize_volume_discount_tier_notification(*, notification_public_id, status):
    notification = (
        VolumeDiscountTierNotification.objects.select_for_update()
        .select_related("customer")
        .filter(
            public_id=notification_public_id,
            status=VolumeDiscountTierNotification.Status.SENDING,
        )
        .first()
    )
    if notification is None:
        return None
    notification.status = status
    notification.sent_at = (
        timezone.now() if status == VolumeDiscountTierNotification.Status.SENT else None
    )
    notification.save(update_fields=["status", "sent_at", "updated_at"])
    return notification


def _audit_volume_discount_delivery(*, notification, action: str) -> None:
    record_event(
        action=action,
        actor=None,
        target=notification,
        metadata={
            "customer_public_id": str(notification.customer.public_id),
            "month": notification.month.isoformat(),
            "threshold_linear_m": f"{notification.threshold_linear_m:.4f}",
        },
    )


def deliver_volume_discount_tier_notification(*, notification_public_id) -> bool:
    """Livre au plus une fois après une prise en charge persistée.

    Un crash ambigu après acceptation SMTP laisse la trace en ``sending`` au lieu
    de provoquer un renvoi automatique potentiellement doublon. L'admin permet
    alors une réconciliation explicite à partir de l'état et de l'horodatage.
    """
    notification = _claim_volume_discount_tier_notification(
        notification_public_id=notification_public_id
    )
    if notification is None:
        return False
    try:
        sent = send_volume_discount_tier_reached_email(notification=notification)
    except Exception:
        failed = _finalize_volume_discount_tier_notification(
            notification_public_id=notification_public_id,
            status=VolumeDiscountTierNotification.Status.FAILED,
        )
        if failed is not None:
            _audit_volume_discount_delivery(
                notification=failed,
                action="customer.volume_discount_tier_notification_failed",
            )
        raise

    status = (
        VolumeDiscountTierNotification.Status.SENT
        if sent
        else VolumeDiscountTierNotification.Status.SKIPPED
    )
    finalized = _finalize_volume_discount_tier_notification(
        notification_public_id=notification_public_id,
        status=status,
    )
    if finalized is None:
        return False
    _audit_volume_discount_delivery(
        notification=finalized,
        action=(
            "customer.volume_discount_tier_notification_sent"
            if sent
            else "customer.volume_discount_tier_notification_skipped"
        ),
    )
    return sent
