from datetime import date
from decimal import Decimal
from unittest.mock import ANY, patch

import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.notifications.models import EmailTemplate, VolumeDiscountTierNotification
from apps.notifications.services.email_templates import EMAIL_TEMPLATE_DEFINITIONS
from apps.notifications.services.transactional import (
    deliver_volume_discount_tier_notification,
    schedule_volume_discount_tier_reached_email,
    send_volume_discount_tier_reached_email,
)
from apps.notifications.tasks import send_volume_discount_tier_reached_email_task
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_volume_tier_task_sends_once_and_marks_notification_sent():
    customer = Customer.objects.create(
        name="Atelier Volume",
        billing_email="volume-client@example.com",
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
    )
    notification = VolumeDiscountTierNotification.objects.create(
        customer=customer,
        month=date(2026, 8, 1),
        threshold_linear_m=Decimal("100.0000"),
        monthly_volume_linear_m=Decimal("125.5000"),
        discount_percent=Decimal("10.00"),
        discount_amount=Decimal("125.50"),
    )

    mail.outbox.clear()
    send_volume_discount_tier_reached_email_task.run(str(notification.public_id))
    send_volume_discount_tier_reached_email_task.run(str(notification.public_id))

    notification.refresh_from_db()
    assert notification.status == VolumeDiscountTierNotification.Status.SENT
    assert notification.sent_at is not None
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["volume-client@example.com"]
    assert "10,00 %" in message.subject
    assert "125,5000" in message.body
    assert "100,0000" in message.body
    assert "ensemble du volume DTF éligible du mois" in message.body
    assert "https://portal.example.test/client/" in message.body
    assert AuditLogEntry.objects.filter(
        action="customer.volume_discount_tier_notification_sent",
        target_public_id=notification.public_id,
    ).exists()


def test_volume_tier_email_is_available_in_atelier_template_catalog():
    definitions = {
        (definition.event, definition.audience): definition
        for definition in EMAIL_TEMPLATE_DEFINITIONS
    }
    definition = definitions[
        (
            EmailTemplate.Event.VOLUME_DISCOUNT_TIER_REACHED,
            EmailTemplate.Audience.CLIENT,
        )
    ]
    assert "volume.discount_percent" in definition.default_subject
    assert "volume.monthly_linear_m" in definition.default_body


@pytest.mark.django_db
def test_volume_tier_schedule_is_after_commit_and_idempotent_per_month_threshold():
    actor = get_user_model().objects.create_user(email="actor-volume@example.com", password="pass")
    customer = Customer.objects.create(
        name="Atelier Idempotent",
        billing_email="idempotent@example.com",
    )
    kwargs = {
        "customer": customer,
        "month": date(2026, 8, 1),
        "threshold_linear_m": Decimal("50.0000"),
        "monthly_volume_linear_m": Decimal("54.0000"),
        "discount_percent": Decimal("7.50"),
        "discount_amount": Decimal("30.00"),
        "actor": actor,
        "source": "test",
    }

    with patch(
        "apps.notifications.tasks.send_volume_discount_tier_reached_email_task.delay"
    ) as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            first, first_created = schedule_volume_discount_tier_reached_email(**kwargs)
            second, second_created = schedule_volume_discount_tier_reached_email(**kwargs)

    assert first.public_id == second.public_id
    assert first_created is True
    assert second_created is False
    delay.assert_called_once_with(str(first.public_id))
    assert VolumeDiscountTierNotification.objects.count() == 1


@pytest.mark.django_db
def test_volume_tier_email_keeps_each_customer_contact_address_private():
    customer = Customer.objects.create(
        name="Atelier Contacts",
        billing_email="billing-contacts@example.com",
    )
    other_customer = Customer.objects.create(name="Autre tenant")
    owner = get_user_model().objects.create_user(email="owner-contacts@example.com")
    admin = get_user_model().objects.create_user(email="admin-contacts@example.com")
    foreign_owner = get_user_model().objects.create_user(email="foreign-owner@example.com")
    CustomerMembership.objects.create(
        customer=customer,
        user=owner,
        role=CustomerMembership.Role.OWNER,
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=admin,
        role=CustomerMembership.Role.ADMIN,
    )
    CustomerMembership.objects.create(
        customer=other_customer,
        user=foreign_owner,
        role=CustomerMembership.Role.OWNER,
    )
    notification = VolumeDiscountTierNotification.objects.create(
        customer=customer,
        month=date(2026, 8, 1),
        threshold_linear_m=Decimal("100.0000"),
        monthly_volume_linear_m=Decimal("110.0000"),
        discount_percent=Decimal("10.00"),
    )

    mail.outbox.clear()
    assert send_volume_discount_tier_reached_email(notification=notification) is True

    assert len(mail.outbox) == 3
    assert {tuple(message.to) for message in mail.outbox} == {
        ("billing-contacts@example.com",),
        ("owner-contacts@example.com",),
        ("admin-contacts@example.com",),
    }
    assert all(len(message.to) == 1 for message in mail.outbox)
    assert all("foreign-owner@example.com" not in message.to for message in mail.outbox)


@pytest.mark.django_db
def test_ambiguous_post_smtp_failure_never_automatically_resends():
    customer = Customer.objects.create(
        name="Atelier Crash",
        billing_email="crash@example.com",
    )
    notification = VolumeDiscountTierNotification.objects.create(
        customer=customer,
        month=date(2026, 8, 1),
        threshold_linear_m=Decimal("80.0000"),
        monthly_volume_linear_m=Decimal("82.0000"),
        discount_percent=Decimal("8.00"),
    )

    with (
        patch(
            "apps.notifications.services.transactional.send_volume_discount_tier_reached_email",
            return_value=True,
        ) as send_email,
        patch(
            "apps.notifications.services.transactional._finalize_volume_discount_tier_notification",
            side_effect=ConnectionError("database unavailable after SMTP"),
        ),
        pytest.raises(ConnectionError, match="database unavailable"),
    ):
        deliver_volume_discount_tier_notification(notification_public_id=notification.public_id)

    notification.refresh_from_db()
    assert notification.status == VolumeDiscountTierNotification.Status.SENDING
    assert notification.attempt_count == 1
    assert (
        deliver_volume_discount_tier_notification(notification_public_id=notification.public_id)
        is False
    )
    send_email.assert_called_once_with(notification=ANY)


@pytest.mark.django_db
def test_immediate_capture_schedules_tier_email_once():
    from apps.billing.models import Payment
    from apps.customers.services.volume_discounts import CustomerVolumeDiscountTierService
    from apps.orders.models import Order
    from django.utils import timezone

    user = get_user_model().objects.create_user(email="cash-tier-mail@example.com", password="pass")
    customer = Customer.objects.create(
        name="Cash Mail",
        billing_email="cash-mail@example.com",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        status=Order.Status.SUBMITTED,
        billing_mode=Order.BillingMode.IMMEDIATE,
        pricing_status=Order.PricingStatus.PRICED,
        source="client_portal",
        currency="EUR",
        total_amount=Decimal("50.00"),
        volume_discount_month=timezone.localdate().replace(day=1),
        monthly_volume_linear_m=Decimal("6.0000"),
        volume_discount_threshold_linear_m=Decimal("5.0000"),
        volume_discount_percent=Decimal("10.00"),
        volume_discount_amount=Decimal("4.00"),
    )
    Payment.objects.create(
        order=order,
        created_by=user,
        provider=Payment.Provider.STRIPE,
        status=Payment.Status.CAPTURED,
        amount=order.total_amount,
        currency=order.currency,
        source="test",
    )

    with patch(
        "apps.notifications.tasks.send_volume_discount_tier_reached_email_task.delay"
    ) as delay:
        with TestCase.captureOnCommitCallbacks(execute=True):
            service = CustomerVolumeDiscountTierService()
            service.notify_immediate_tier_after_capture(
                order=order,
                actor=user,
                source="test",
            )
            service.notify_immediate_tier_after_capture(
                order=order,
                actor=user,
                source="test",
            )

    assert VolumeDiscountTierNotification.objects.filter(customer=customer).count() == 1
    assert delay.call_count == 1
