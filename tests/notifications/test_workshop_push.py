from __future__ import annotations

import base64
import logging
import socket
import sys
import traceback
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from apps.accounts.models import StaffMembership
from apps.auditlog.models import AuditLogEntry
from apps.customers.models import Customer
from apps.notifications.models import (
    PushDelivery,
    StaffPushSubscription,
    WorkshopNotificationEvent,
)
from apps.notifications.services.push_crypto import PushSubscriptionCrypto
from apps.notifications.services.web_push_client import (
    PushEndpointValidationError,
    WebPushClient,
    WebPushConfiguration,
    WebPushGone,
    WebPushPermanentError,
    WebPushTransientError,
    validate_push_endpoint,
    validate_subscription_keys,
)
from apps.notifications.services.workshop_push import WorkshopNotificationService
from apps.orders.models import Order
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

FERNET_KEY = Fernet.generate_key().decode("ascii")
P256DH = base64.urlsafe_b64encode(b"\x04" + (b"p" * 64)).rstrip(b"=").decode("ascii")
AUTH_SECRET = base64.urlsafe_b64encode(b"a" * 16).rstrip(b"=").decode("ascii")
WEB_PUSH_SETTINGS = {
    "WEB_PUSH_ENABLED": True,
    "WEB_PUSH_VAPID_PUBLIC_KEY": "public-vapid-test-key",
    "WEB_PUSH_VAPID_PRIVATE_KEY": "private-vapid-test-key",
    "WEB_PUSH_VAPID_CONTACT": "mailto:atelier@example.com",
    "WEB_PUSH_ENCRYPTION_KEYS": [f"v1:{FERNET_KEY}"],
    "WEB_PUSH_ALLOWED_DOMAINS": ["fcm.googleapis.com"],
}
ENDPOINT = "https://fcm.googleapis.com/fcm/send/browser-token"


def _public_resolver(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]


class FakePushClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.configuration = Mock()
        self.sent: list[dict] = []

    def send(self, **kwargs) -> None:
        self.sent.append(kwargs)
        if self.error:
            raise self.error


def _staff(*, email: str = "staff@example.com", permissions: bool = True):
    user = get_user_model().objects.create_user(
        email=email,
        password="pass",
        is_staff=True,
    )
    membership = StaffMembership.objects.create(user=user)
    if permissions:
        for app_label, codename in (
            ("accounts", "access_staff_portal"),
            ("orders", "view_order"),
            ("production", "view_productionjob"),
        ):
            user.user_permissions.add(
                Permission.objects.get(
                    content_type__app_label=app_label,
                    codename=codename,
                )
            )
    return user, membership


def _order(*, actor=None, customer_name: str = "Client A") -> Order:
    customer = Customer.objects.create(name=customer_name)
    return Order.objects.create(
        customer=customer,
        created_by=actor,
        status=Order.Status.SUBMITTED,
    )


def _subscription(*, membership: StaffMembership, endpoint: str = ENDPOINT):
    crypto = PushSubscriptionCrypto([f"v1:{FERNET_KEY}"])
    return StaffPushSubscription.objects.create(
        staff_membership=membership,
        endpoint_ciphertext=crypto.encrypt(endpoint),
        endpoint_digest=crypto.endpoint_digest(endpoint),
        p256dh_ciphertext=crypto.encrypt(P256DH),
        auth_ciphertext=crypto.encrypt(AUTH_SECRET),
        last_seen_at=timezone.now(),
    )


def _delivery(*, membership: StaffMembership, actor=None) -> PushDelivery:
    order = _order(actor=actor)
    event = WorkshopNotificationEvent.objects.create(
        event_type=WorkshopNotificationEvent.EventType.ORDER_SUBMITTED,
        customer=order.customer,
        order=order,
        actor=actor,
        source="test",
    )
    return PushDelivery.objects.create(
        event=event,
        subscription=_subscription(membership=membership),
    )


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_subscription_material_is_encrypted_and_audited():
    actor, membership = _staff()
    client = FakePushClient()
    service = WorkshopNotificationService(client=client)

    with patch(
        "apps.notifications.services.workshop_push.validate_push_endpoint",
        return_value=ENDPOINT,
    ):
        subscription = service.subscribe(
            actor=actor,
            endpoint=ENDPOINT,
            p256dh=P256DH,
            auth=AUTH_SECRET,
            source="portal",
        )

    subscription.refresh_from_db()
    stored = " ".join(
        (
            subscription.endpoint_ciphertext,
            subscription.p256dh_ciphertext,
            subscription.auth_ciphertext,
        )
    )
    assert ENDPOINT not in stored
    assert P256DH not in stored
    assert AUTH_SECRET not in stored
    assert subscription.staff_membership == membership
    assert AuditLogEntry.objects.filter(
        action="workshop_push.subscription_created",
        target_public_id=subscription.public_id,
    ).exists()


def test_versioned_crypto_decrypts_with_rotated_key():
    old_key = Fernet.generate_key().decode("ascii")
    old_crypto = PushSubscriptionCrypto([f"v1:{old_key}"])
    encrypted = old_crypto.encrypt("secret")

    rotated = PushSubscriptionCrypto([f"v2:{FERNET_KEY}", f"v1:{old_key}"])

    assert rotated.decrypt(encrypted) == "secret"
    assert rotated.encrypt("new-secret").startswith("v2:")


@pytest.mark.parametrize(
    "endpoint",
    (
        "http://fcm.googleapis.com/fcm/send/token",
        "https://127.0.0.1/push",
        "https://localhost/push",
        "https://evil.example/push",
        "https://user:password@fcm.googleapis.com/push",
    ),
)
def test_endpoint_validation_rejects_unsafe_urls(endpoint):
    with pytest.raises(PushEndpointValidationError):
        validate_push_endpoint(
            endpoint,
            allowed_domains=["fcm.googleapis.com"],
            resolver=lambda *_args, **_kwargs: [],
        )


def test_endpoint_validation_rejects_private_dns_resolution():
    def resolver(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.10", 443))]

    with pytest.raises(PushEndpointValidationError):
        validate_push_endpoint(
            ENDPOINT,
            allowed_domains=["fcm.googleapis.com"],
            resolver=resolver,
        )


def test_endpoint_validation_accepts_allowlisted_public_resolution():
    def resolver(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]

    assert (
        validate_push_endpoint(
            ENDPOINT,
            allowed_domains=["fcm.googleapis.com"],
            resolver=resolver,
        )
        == ENDPOINT
    )


@pytest.mark.parametrize(
    ("p256dh", "auth"),
    (
        ("not-base64!", AUTH_SECRET),
        (base64.urlsafe_b64encode(b"short").decode("ascii"), AUTH_SECRET),
        (P256DH, "not-base64!"),
        (P256DH, base64.urlsafe_b64encode(b"short").decode("ascii")),
    ),
)
def test_subscription_keys_require_base64url_and_expected_lengths(p256dh, auth):
    with pytest.raises(PushEndpointValidationError):
        validate_subscription_keys(p256dh=p256dh, auth=auth)


@override_settings(**WEB_PUSH_SETTINGS)
@pytest.mark.parametrize(
    ("status_code", "error_type"),
    (
        (404, WebPushGone),
        (410, WebPushGone),
        (429, WebPushTransientError),
        (503, WebPushTransientError),
        (400, WebPushPermanentError),
    ),
)
def test_pywebpush_provider_status_is_classified_without_secret_leak(status_code, error_type):
    class ProviderException(Exception):
        def __init__(self):
            super().__init__(f"provider exposed {ENDPOINT} browser-auth-secret")
            self.response = SimpleNamespace(status_code=status_code)

    def fail_webpush(**_kwargs):
        raise ProviderException

    fake_module = SimpleNamespace(WebPushException=ProviderException, webpush=fail_webpush)
    configuration = WebPushConfiguration.from_settings()
    with (
        patch.dict(sys.modules, {"pywebpush": fake_module}),
        pytest.raises(error_type) as caught,
    ):
        WebPushClient(configuration, resolver=_public_resolver).send(
            endpoint=ENDPOINT,
            p256dh="browser-public-key",
            auth="browser-auth-secret",
            payload={"title": "generic"},
        )

    assert ENDPOINT not in str(caught.value)
    assert "browser-auth-secret" not in str(caught.value)


@override_settings(**WEB_PUSH_SETTINGS)
def test_transport_rejects_dns_rebinding_before_post():
    resolutions = iter(
        (
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))],
        )
    )

    def changing_resolver(*_args, **_kwargs):
        return next(resolutions)

    class ProviderException(Exception):
        pass

    def invoke_transport(**kwargs):
        kwargs["requests_session"].post(kwargs["subscription_info"]["endpoint"])

    fake_module = SimpleNamespace(WebPushException=ProviderException, webpush=invoke_transport)
    with (
        patch.dict(sys.modules, {"pywebpush": fake_module}),
        patch("requests.Session.post") as network_post,
        pytest.raises(PushEndpointValidationError, match="resolution changed"),
    ):
        WebPushClient(
            WebPushConfiguration.from_settings(),
            resolver=changing_resolver,
        ).send(
            endpoint=ENDPOINT,
            p256dh="browser-public-key",
            auth="browser-auth-secret",
            payload={"title": "generic"},
        )
    network_post.assert_not_called()


@override_settings(**WEB_PUSH_SETTINGS)
def test_transport_never_follows_redirect_to_private_location():
    class ProviderException(Exception):
        def __init__(self, response):
            self.response = response

    def invoke_transport(**kwargs):
        response = kwargs["requests_session"].post(kwargs["subscription_info"]["endpoint"])
        raise ProviderException(response)

    response = SimpleNamespace(
        status_code=307,
        reason="Temporary Redirect",
        text="",
        headers={"Location": "http://127.0.0.1/internal"},
    )
    fake_module = SimpleNamespace(WebPushException=ProviderException, webpush=invoke_transport)
    with (
        patch.dict(sys.modules, {"pywebpush": fake_module}),
        patch("requests.Session.post", return_value=response) as network_post,
        pytest.raises(WebPushPermanentError),
    ):
        WebPushClient(
            WebPushConfiguration.from_settings(),
            resolver=_public_resolver,
        ).send(
            endpoint=ENDPOINT,
            p256dh="browser-public-key",
            auth="browser-auth-secret",
            payload={"title": "generic"},
        )

    network_post.assert_called_once()
    assert network_post.call_args.args[0] == ENDPOINT
    assert network_post.call_args.kwargs["allow_redirects"] is False


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_order_submitted_event_and_fanout_are_idempotent_after_commit():
    actor, membership = _staff()
    order = _order(actor=actor)
    _subscription(membership=membership)
    client = FakePushClient()
    service = WorkshopNotificationService(client=client)

    with patch.object(service, "_schedule_fanout") as schedule:
        with TestCase.captureOnCommitCallbacks(execute=True):
            first = service.publish_order_submitted(order, actor, "test")
        with TestCase.captureOnCommitCallbacks(execute=True):
            second = service.publish_order_submitted(order, actor, "test")

    assert first == second
    assert WorkshopNotificationEvent.objects.count() == 1
    schedule.assert_called_once_with(str(first.public_id))

    with patch.object(service, "_schedule_deliveries") as schedule_deliveries:
        with TestCase.captureOnCommitCallbacks(execute=True):
            assert service.fanout(event_public_id=first.public_id) == 1
        with TestCase.captureOnCommitCallbacks(execute=True):
            assert service.fanout(event_public_id=first.public_id) == 0
    delivery = PushDelivery.objects.get()
    schedule_deliveries.assert_called_once_with([str(delivery.public_id)])
    assert ENDPOINT not in repr(schedule_deliveries.call_args)


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_existing_event_cannot_be_rebound_across_customers():
    actor, _ = _staff()
    order = _order(actor=actor, customer_name="Original tenant")
    other_customer = Customer.objects.create(name="Other tenant")
    WorkshopNotificationEvent.objects.create(
        event_type=WorkshopNotificationEvent.EventType.ORDER_SUBMITTED,
        customer=other_customer,
        order=order,
        actor=actor,
        source="corrupt-fixture",
    )

    with pytest.raises(ValidationError, match="tenant"):
        WorkshopNotificationService(client=FakePushClient()).publish_order_submitted(
            order,
            actor,
            "test",
        )


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_revoked_permission_is_rechecked_before_delivery():
    actor, membership = _staff()
    delivery = _delivery(membership=membership, actor=actor)
    actor.user_permissions.clear()
    client = FakePushClient()

    result = WorkshopNotificationService(client=client).deliver(
        delivery_public_id=delivery.public_id
    )

    delivery.refresh_from_db()
    assert result == PushDelivery.Status.SKIPPED
    assert delivery.status == PushDelivery.Status.SKIPPED
    assert delivery.failure_code == "access_revoked"
    assert client.sent == []


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_deactivated_staff_membership_is_rechecked_after_fanout():
    actor, membership = _staff()
    order = _order(actor=actor)
    event = WorkshopNotificationService(client=FakePushClient()).publish_order_submitted(
        order,
        actor,
        "test",
    )
    _subscription(membership=membership)
    service = WorkshopNotificationService(client=FakePushClient())
    with patch.object(service, "_schedule_deliveries"):
        with TestCase.captureOnCommitCallbacks(execute=True):
            assert service.fanout(event_public_id=event.public_id) == 1
    delivery = PushDelivery.objects.get(event=event)
    membership.is_active = False
    membership.save(update_fields=("is_active", "updated_at"))

    result = service.deliver(delivery_public_id=delivery.public_id)

    delivery.refresh_from_db()
    assert result == PushDelivery.Status.SKIPPED
    assert delivery.status == PushDelivery.Status.SKIPPED
    assert delivery.failure_code == "access_revoked"
    assert service._client.sent == []


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_unsubscribe_cannot_cross_staff_memberships():
    owner, owner_membership = _staff(email="owner@example.com")
    other, _ = _staff(email="other@example.com")
    subscription = _subscription(membership=owner_membership)

    with pytest.raises(PermissionDenied):
        WorkshopNotificationService(client=FakePushClient()).unsubscribe(
            actor=other,
            subscription_public_id=subscription.public_id,
            source="portal",
        )
    subscription.refresh_from_db()
    assert subscription.is_active is True


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_unsubscribe_erases_encrypted_subscription_material():
    actor, membership = _staff()
    subscription = _subscription(membership=membership)

    assert WorkshopNotificationService(client=FakePushClient()).unsubscribe(
        actor=actor,
        subscription_public_id=subscription.public_id,
        source="portal",
    )

    subscription.refresh_from_db()
    assert subscription.is_active is False
    assert subscription.endpoint_ciphertext == ""
    assert subscription.p256dh_ciphertext == ""
    assert subscription.auth_ciphertext == ""


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS, WEB_PUSH_MAX_ACTIVE_SUBSCRIPTIONS_PER_MEMBER=1)
def test_active_subscription_quota_is_enforced_per_member():
    actor, _ = _staff()
    service = WorkshopNotificationService(client=FakePushClient())
    with patch(
        "apps.notifications.services.workshop_push.validate_push_endpoint",
        side_effect=lambda endpoint: endpoint,
    ):
        first = service.subscribe(
            actor=actor,
            endpoint=ENDPOINT,
            p256dh=P256DH,
            auth=AUTH_SECRET,
            source="portal",
        )
        with pytest.raises(ValidationError, match="limit"):
            service.subscribe(
                actor=actor,
                endpoint="https://fcm.googleapis.com/fcm/send/second-token",
                p256dh=P256DH,
                auth=AUTH_SECRET,
                source="portal",
            )
        refreshed = service.subscribe(
            actor=actor,
            endpoint=ENDPOINT,
            p256dh=P256DH,
            auth=AUTH_SECRET,
            source="portal",
        )

    assert refreshed.public_id == first.public_id
    assert StaffPushSubscription.objects.filter(is_active=True).count() == 1


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
@pytest.mark.parametrize(
    ("error", "expected_status", "subscription_active"),
    (
        (WebPushGone(code="subscription_gone", status_code=410), PushDelivery.Status.GONE, False),
        (
            WebPushPermanentError(code="provider_rejected", status_code=400),
            PushDelivery.Status.FAILED,
            True,
        ),
    ),
)
def test_provider_terminal_statuses(error, expected_status, subscription_active):
    actor, membership = _staff()
    delivery = _delivery(membership=membership, actor=actor)

    result = WorkshopNotificationService(client=FakePushClient(error)).deliver(
        delivery_public_id=delivery.public_id
    )

    delivery.refresh_from_db()
    delivery.subscription.refresh_from_db()
    assert result == expected_status
    assert delivery.status == expected_status
    assert delivery.subscription.is_active is subscription_active


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_transient_provider_failure_is_persisted_for_retry():
    actor, membership = _staff()
    delivery = _delivery(membership=membership, actor=actor)
    error = WebPushTransientError(code="provider_temporarily_unavailable", status_code=503)

    with pytest.raises(WebPushTransientError):
        WorkshopNotificationService(client=FakePushClient(error)).deliver(
            delivery_public_id=delivery.public_id
        )

    delivery.refresh_from_db()
    assert delivery.status == PushDelivery.Status.RETRY
    assert delivery.next_attempt_at is not None
    assert delivery.failure_code == "provider_temporarily_unavailable"


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_unexpected_delivery_exception_is_sanitized_without_exception_chain():
    actor, membership = _staff()
    delivery = _delivery(membership=membership, actor=actor)
    secret_error = RuntimeError(f"failed {ENDPOINT} {AUTH_SECRET}")

    with pytest.raises(WebPushTransientError) as caught:
        WorkshopNotificationService(client=FakePushClient(secret_error)).deliver(
            delivery_public_id=delivery.public_id
        )

    rendered = "".join(
        traceback.format_exception(
            type(caught.value),
            caught.value,
            caught.value.__traceback__,
        )
    )
    assert str(caught.value) == "delivery_error"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert ENDPOINT not in rendered
    assert AUTH_SECRET not in rendered


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS, WEB_PUSH_CLAIM_TIMEOUT_SECONDS=60)
def test_recovery_releases_stale_claim_and_schedules_public_id_only():
    actor, membership = _staff()
    delivery = _delivery(membership=membership, actor=actor)
    PushDelivery.objects.filter(pk=delivery.pk).update(
        status=PushDelivery.Status.SENDING,
        claimed_at=timezone.now() - timedelta(minutes=2),
    )
    service = WorkshopNotificationService(client=FakePushClient())

    with patch.object(service, "_schedule_deliveries") as schedule:
        with TestCase.captureOnCommitCallbacks(execute=True):
            count = service.recover_stale_deliveries()

    delivery.refresh_from_db()
    assert count == 1
    assert delivery.status == PushDelivery.Status.RETRY
    schedule.assert_called_once_with([str(delivery.public_id)])


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_success_payload_has_no_customer_data_and_task_args_use_public_ids(caplog):
    actor, membership = _staff()
    delivery = _delivery(membership=membership, actor=actor)
    client = FakePushClient()
    caplog.set_level(logging.DEBUG)

    result = WorkshopNotificationService(client=client).deliver(
        delivery_public_id=delivery.public_id
    )

    assert result == PushDelivery.Status.SENT
    payload = client.sent[0]["payload"]
    assert payload == {
        "title": "Nouvelle commande Atelier",
        "body": "Une nouvelle commande est disponible.",
        "tag": f"workshop-{delivery.event.public_id}",
        "url": "/staff/",
        "event_public_id": str(delivery.event.public_id),
    }
    serialized = repr(client.sent)
    assert delivery.event.customer.name not in serialized
    assert "browser-auth-secret" not in caplog.text
    assert ENDPOINT not in caplog.text


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_polling_starts_from_baseline_and_returns_only_new_events():
    actor, _ = _staff()
    service = WorkshopNotificationService(client=FakePushClient())
    first_order = _order(actor=actor, customer_name="First")
    first = service.publish_order_submitted(first_order, actor, "test")

    baseline = service.read_recent_events(actor=actor)
    assert [event.public_id for event in baseline.events] == [str(first.public_id)]
    assert baseline.cursor == str(first.public_id)

    second_order = _order(actor=actor, customer_name="Second")
    second = service.publish_order_submitted(second_order, actor, "test")
    page = service.read_recent_events(actor=actor, cursor=baseline.cursor)
    assert [event.public_id for event in page.events] == [str(second.public_id)]
    assert page.cursor == str(second.public_id)


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS)
def test_empty_polling_baseline_does_not_swallow_first_future_event():
    actor, _ = _staff()
    service = WorkshopNotificationService(client=FakePushClient())
    empty = service.read_recent_events(actor=actor)
    assert empty.events == ()
    assert empty.cursor is None

    order = _order(actor=actor)
    event = service.publish_order_submitted(order, actor, "test")
    first_future_page = service.read_recent_events(actor=actor, cursor=empty.cursor)
    assert [item.public_id for item in first_future_page.events] == [str(event.public_id)]


@pytest.mark.django_db
@override_settings(**WEB_PUSH_SETTINGS, WEB_PUSH_RETENTION_DAYS=7)
def test_retention_purges_old_events_and_inactive_subscriptions_only():
    actor, membership = _staff()
    old_delivery = _delivery(membership=membership, actor=actor)
    subscription = old_delivery.subscription
    subscription.is_active = False
    subscription.disabled_at = timezone.now() - timedelta(days=8)
    subscription.save(update_fields=("is_active", "disabled_at", "updated_at"))
    WorkshopNotificationEvent.objects.filter(pk=old_delivery.event_id).update(
        created_at=timezone.now() - timedelta(days=8)
    )
    active = _subscription(
        membership=membership,
        endpoint="https://fcm.googleapis.com/fcm/send/active-token",
    )

    WorkshopNotificationService(client=FakePushClient()).purge_history()

    assert not WorkshopNotificationEvent.objects.filter(pk=old_delivery.event_id).exists()
    assert not StaffPushSubscription.objects.filter(pk=subscription.pk).exists()
    assert StaffPushSubscription.objects.filter(pk=active.pk).exists()


@pytest.mark.django_db
def test_subscription_state_requires_all_workshop_permissions():
    actor, _ = _staff(permissions=False)

    with pytest.raises(PermissionDenied):
        WorkshopNotificationService(client=FakePushClient()).subscription_state(actor=actor)
