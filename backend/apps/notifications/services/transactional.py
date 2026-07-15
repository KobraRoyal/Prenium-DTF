from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse

from apps.notifications.models import EmailTemplate
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
    blocked_domains: set[str] = set()
    for recipient in recipients:
        domain = recipient.strip().lower().rpartition("@")[2]
        if domain in _RESERVED_EMAIL_DOMAINS or domain.endswith(_RESERVED_EMAIL_SUFFIXES):
            blocked_domains.add(domain or "missing-domain")
            continue
        safe_recipients.append(recipient)

    if blocked_domains:
        logger.warning(
            "Blocked reserved QA recipient domain(s) for %s/%s: %s",
            event,
            audience,
            ", ".join(sorted(blocked_domains)),
        )
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
