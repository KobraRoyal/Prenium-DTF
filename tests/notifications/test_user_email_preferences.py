import pytest
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer, CustomerMembership
from apps.notifications.models import EmailTemplate, UserEmailNotificationMute
from apps.notifications.services.email_templates import EmailTemplateService
from apps.notifications.services.preferences import user_email_preference_service
from apps.notifications.services.transactional import (
    send_order_awaiting_payment_email,
    send_order_created_email,
    send_order_priced_email,
)
from apps.orders.models import Order
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse

OPTIONAL_EVENTS = (
    EmailTemplate.Event.ORDER_CREATED,
    EmailTemplate.Event.ORDER_PROCESSING,
    EmailTemplate.Event.ORDER_READY_TO_SHIP,
    EmailTemplate.Event.ORDER_READY_FOR_PICKUP,
    EmailTemplate.Event.ORDER_SHIPPED,
    EmailTemplate.Event.ORDER_PRICED,
    EmailTemplate.Event.VOLUME_DISCOUNT_TIER_REACHED,
)


def create_order(*, email="owner@example.com", billing_email="billing@example.com"):
    user = get_user_model().objects.create_user(email=email, password="pass")
    customer = Customer.objects.create(name="Atelier Démo", billing_email=billing_email)
    order = Order.objects.create(
        customer=customer,
        created_by=user,
        total_amount="125.50",
        currency="EUR",
        billing_mode=Order.BillingMode.DEFERRED,
    )
    return user, order


@pytest.mark.django_db
@override_settings(INTERNAL_NOTIFICATION_EMAILS=["atelier@example.com"])
def test_missing_preference_still_sends_the_client_email():
    user, order = create_order()

    mail.outbox.clear()
    send_order_created_email(order=order)

    recipients = {address for message in mail.outbox for address in message.to}
    assert user.email in recipients
    assert "billing@example.com" in recipients
    assert "atelier@example.com" in recipients


@pytest.mark.django_db
@override_settings(INTERNAL_NOTIFICATION_EMAILS=["atelier@example.com"])
def test_mute_drops_only_the_matching_user_address():
    user, order = create_order()
    other = get_user_model().objects.create_user(email="other@example.com", password="pass")
    user_email_preference_service.replace_mutes(
        user=user,
        enabled_events=[
            event for event in OPTIONAL_EVENTS if event != EmailTemplate.Event.ORDER_CREATED
        ],
    )

    mail.outbox.clear()
    send_order_created_email(order=order)

    recipients = [address for message in mail.outbox for address in message.to]
    assert user.email not in recipients
    assert "billing@example.com" in recipients
    assert "atelier@example.com" in recipients
    assert not other.email_notification_mutes.exists()


@pytest.mark.django_db
def test_mandatory_payment_email_ignores_a_stored_mute():
    user, order = create_order()
    order.billing_mode = Order.BillingMode.IMMEDIATE
    order.pricing_status = Order.PricingStatus.PRICED
    order.save(update_fields=["billing_mode", "pricing_status", "updated_at"])
    order.refresh_from_db()
    UserEmailNotificationMute.objects.create(
        user=user,
        event=EmailTemplate.Event.ORDER_AWAITING_PAYMENT,
    )

    mail.outbox.clear()
    send_order_awaiting_payment_email(order=order)

    recipients = {address for message in mail.outbox for address in message.to}
    assert user.email in recipients


@pytest.mark.django_db
def test_replace_mutes_rejects_mandatory_events_and_audits_the_change():
    user = get_user_model().objects.create_user(email="prefs@example.com", password="pass")

    user_email_preference_service.replace_mutes(
        user=user,
        enabled_events=["password_reset", EmailTemplate.Event.ORDER_AWAITING_PAYMENT],
        ip_address="127.0.0.1",
    )

    expected = set(OPTIONAL_EVENTS) - {EmailTemplate.Event.ORDER_PRICED}
    muted = set(user.email_notification_mutes.values_list("event", flat=True))
    assert muted == expected
    audit = AuditLogEntry.objects.get(action="notifications.email_preference.updated")
    assert audit.actor_id == user.id
    assert audit.target_public_id == user.public_id
    assert audit.metadata["muted_events"] == sorted(expected)
    assert "password_reset" not in audit.metadata["muted_events"]

    user_email_preference_service.replace_mutes(user=user, enabled_events=[])
    audits = AuditLogEntry.objects.filter(action="notifications.email_preference.updated")
    assert audits.count() == 1


@pytest.mark.django_db
def test_inactive_atelier_template_stays_hidden_and_its_mute_is_kept():
    user = get_user_model().objects.create_user(email="hidden@example.com", password="pass")
    UserEmailNotificationMute.objects.create(
        user=user,
        event=EmailTemplate.Event.ORDER_SHIPPED,
    )
    EmailTemplateService().save_override(
        event=EmailTemplate.Event.ORDER_SHIPPED,
        audience=EmailTemplate.Audience.CLIENT,
        subject_template="Commande {{ order.reference }}",
        body_template="Bonjour {{ customer.name }}",
        is_active=False,
        actor=user,
    )

    visible = {choice.event for choice in user_email_preference_service.visible_choices(user=user)}
    assert EmailTemplate.Event.ORDER_SHIPPED not in visible
    assert EmailTemplate.Event.ORDER_CREATED in visible

    user_email_preference_service.replace_mutes(user=user, enabled_events=list(visible))

    mutes = user.email_notification_mutes
    assert mutes.filter(event=EmailTemplate.Event.ORDER_SHIPPED).exists()
    assert not mutes.filter(event=EmailTemplate.Event.ORDER_CREATED).exists()


@pytest.mark.django_db
def test_profile_lists_only_active_optional_notifications_and_saves_the_signed_in_user():
    user = get_user_model().objects.create_user(email="portal-prefs@example.com", password="pass")
    other = get_user_model().objects.create_user(email="portal-other@example.com", password="pass")
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(reverse("portal:profile"))
    html = response.content.decode()

    assert response.status_code == 200
    assert 'id="account-notifications"' in html
    assert 'id="email-pref-order_created"' in html
    assert 'id="email-pref-order_priced"' not in html
    assert 'role="switch"' in html
    assert 'id="email-pref-volume_discount_tier_reached"' in html
    assert 'id="email-pref-order_awaiting_payment"' not in html
    assert 'id="email-pref-password_reset"' not in html
    assert 'id="email-pref-file_correction_requested"' not in html

    kept = [event for event in OPTIONAL_EVENTS if event != EmailTemplate.Event.ORDER_CREATED]
    saved = client.post(
        reverse("portal:profile-email-notifications"),
        {"space": "client", "enabled_events": kept},
    )

    assert saved.status_code == 302
    assert saved.url.endswith("?space=client&notifications_saved=1#account-notifications")
    assert list(user.email_notification_mutes.values_list("event", flat=True)) == [
        EmailTemplate.Event.ORDER_CREATED
    ]
    assert not other.email_notification_mutes.exists()

    follow = client.get(saved.url.split("#", 1)[0])
    assert "Vos notifications ont été enregistrées." in follow.content.decode()
    assert 'id="email-pref-order_created"' in follow.content.decode()
    assert (
        "checked"
        not in follow.content.decode()
        .split('id="email-pref-order_created"')[1]
        .split("</label>")[0]
    )


@pytest.mark.django_db
def test_staff_profile_shows_the_same_notification_section():
    user = get_user_model().objects.create_user(
        email="staff-prefs@example.com",
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(f"{reverse('portal:profile')}?space=staff")
    html = response.content.decode()

    assert response.status_code == 200
    assert 'id="account-notifications"' in html
    assert "#account-notifications" in html
    assert 'name="space" value="staff"' in html


@pytest.mark.django_db
def test_deferred_collaborator_sees_and_can_mute_priced_notice():
    member = get_user_model().objects.create_user(email="collab@example.com", password="pass")
    customer = Customer.objects.create(
        name="Encours",
        billing_email="billing@example.com",
        default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
    )
    CustomerMembership.objects.create(
        customer=customer,
        user=member,
        role=CustomerMembership.Role.MEMBER,
    )
    EmailTemplateService().save_override(
        event=EmailTemplate.Event.ORDER_PRICED,
        audience=EmailTemplate.Audience.CLIENT,
        subject_template="Tarif {{ order.reference }}",
        body_template="Bonjour {{ customer.name }}",
        is_active=False,
        actor=member,
    )

    visible = {
        choice.event for choice in user_email_preference_service.visible_choices(user=member)
    }
    assert EmailTemplate.Event.ORDER_PRICED in visible

    card_user = get_user_model().objects.create_user(email="card@example.com", password="pass")
    card_customer = Customer.objects.create(
        name="Carte",
        billing_email="card-billing@example.com",
        default_billing_mode=Customer.DefaultBillingMode.IMMEDIATE,
    )
    CustomerMembership.objects.create(
        customer=card_customer,
        user=card_user,
        role=CustomerMembership.Role.MEMBER,
    )
    card_visible = {
        choice.event for choice in user_email_preference_service.visible_choices(user=card_user)
    }
    assert EmailTemplate.Event.ORDER_PRICED not in card_visible

    client = Client()
    assert client.login(email=member.email, password="pass")
    page = client.get(reverse("portal:profile"))
    assert 'id="email-pref-order_priced"' in page.content.decode()
    assert 'role="switch"' in page.content.decode()

    EmailTemplate.objects.filter(
        event=EmailTemplate.Event.ORDER_PRICED,
        audience=EmailTemplate.Audience.CLIENT,
    ).update(is_active=True)
    kept = [event for event in visible if event != EmailTemplate.Event.ORDER_PRICED]
    user_email_preference_service.replace_mutes(user=member, enabled_events=kept)
    order = Order.objects.create(
        customer=customer,
        created_by=member,
        total_amount="80.00",
        currency="EUR",
        billing_mode=Order.BillingMode.DEFERRED,
    )

    mail.outbox.clear()
    send_order_priced_email(order=order)

    recipients = [address for message in mail.outbox for address in message.to]
    assert member.email not in recipients
    assert "billing@example.com" in recipients
