from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.accounts.models import StaffMembership
from apps.accounts.services.access import AccessScopeService
from apps.auditlog.services import record_event
from apps.notifications.models import (
    PushDelivery,
    StaffPushSubscription,
    WorkshopNotificationEvent,
)
from apps.notifications.services.push_crypto import PushSubscriptionCrypto
from apps.notifications.services.web_push_client import (
    WebPushClient,
    WebPushGone,
    WebPushPermanentError,
    WebPushTransientError,
    validate_push_endpoint,
    validate_subscription_keys,
)


class WorkshopPushDisabled(RuntimeError):
    pass


class WorkshopPushConfigurationError(WorkshopPushDisabled, ImproperlyConfigured):
    pass


@dataclass(frozen=True)
class WorkshopSubscriptionSummary:
    public_id: str
    last_seen_at: str


@dataclass(frozen=True)
class WorkshopSubscriptionState:
    enabled: bool
    configured: bool
    vapid_public_key: str
    subscriptions: tuple[WorkshopSubscriptionSummary, ...]


@dataclass(frozen=True)
class WorkshopEventSummary:
    public_id: str
    event_type: str
    created_at: str


@dataclass(frozen=True)
class WorkshopEventPage:
    events: tuple[WorkshopEventSummary, ...]
    cursor: str | None


class WorkshopNotificationService:
    """Own workshop subscriptions, events and reliable Web Push delivery."""

    required_permissions = (
        "orders.view_order",
        "production.view_productionjob",
    )

    def __init__(
        self,
        *,
        crypto: PushSubscriptionCrypto | None = None,
        client: WebPushClient | None = None,
        access_service: AccessScopeService | None = None,
    ) -> None:
        self._crypto = crypto
        self._client = client
        self.access_service = access_service or AccessScopeService()

    def subscription_state(self, *, actor) -> WorkshopSubscriptionState:
        membership = self._require_workshop_access(actor)
        configured = self._configuration_is_valid()
        subscriptions = tuple(
            WorkshopSubscriptionSummary(
                public_id=str(subscription.public_id),
                last_seen_at=subscription.last_seen_at.isoformat(),
            )
            for subscription in StaffPushSubscription.objects.filter(
                staff_membership=membership,
                is_active=True,
            )
        )
        return WorkshopSubscriptionState(
            enabled=settings.WEB_PUSH_ENABLED,
            configured=configured,
            vapid_public_key=(settings.WEB_PUSH_VAPID_PUBLIC_KEY if configured else ""),
            subscriptions=subscriptions,
        )

    @transaction.atomic
    def subscribe(
        self,
        *,
        actor,
        endpoint: str,
        p256dh: str,
        auth: str,
        source: str,
    ) -> StaffPushSubscription:
        self._require_enabled_configuration()
        membership = self._require_workshop_access(actor)
        endpoint = endpoint.strip()
        if not endpoint or not p256dh or not auth:
            raise ValidationError("Incomplete Web Push subscription")
        if len(endpoint) > 4096 or len(p256dh) > 512 or len(auth) > 512:
            raise ValidationError("Web Push subscription is too large")
        validate_subscription_keys(p256dh=p256dh, auth=auth)
        validate_push_endpoint(endpoint)
        crypto = self._get_crypto()
        digest = crypto.endpoint_digest(endpoint)
        now = timezone.now()
        membership = StaffMembership.objects.select_for_update().get(pk=membership.pk)
        if not membership.is_active or not self._has_required_permissions(actor):
            raise PermissionDenied("Workshop notification access denied")
        existing = (
            StaffPushSubscription.objects.select_for_update().filter(endpoint_digest=digest).first()
        )
        if (
            existing is not None
            and existing.is_active
            and existing.staff_membership_id != membership.id
        ):
            raise ValidationError("This Web Push subscription is already registered")
        activates_new_slot = existing is None or not existing.is_active
        if (
            activates_new_slot
            and StaffPushSubscription.objects.filter(
                staff_membership=membership,
                is_active=True,
            ).count()
            >= settings.WEB_PUSH_MAX_ACTIVE_SUBSCRIPTIONS_PER_MEMBER
        ):
            raise ValidationError("Active Web Push subscription limit reached")

        values = {
            "staff_membership": membership,
            "endpoint_ciphertext": crypto.encrypt(endpoint),
            "p256dh_ciphertext": crypto.encrypt(p256dh),
            "auth_ciphertext": crypto.encrypt(auth),
            "is_active": True,
            "last_seen_at": now,
            "disabled_at": None,
            "consecutive_failures": 0,
            "last_failure_code": "",
        }
        if existing is None:
            subscription = StaffPushSubscription.objects.create(endpoint_digest=digest, **values)
            action = "workshop_push.subscription_created"
        else:
            for field, value in values.items():
                setattr(existing, field, value)
            existing.save(update_fields=(*values.keys(), "updated_at"))
            subscription = existing
            action = "workshop_push.subscription_refreshed"
        record_event(
            action=action,
            actor=actor,
            target=subscription,
            metadata={"source": self._safe_source(source)},
        )
        return subscription

    @transaction.atomic
    def unsubscribe(
        self,
        *,
        actor,
        subscription_public_id: UUID | str,
        source: str,
    ) -> bool:
        membership = self._require_workshop_access(actor)
        subscription = (
            StaffPushSubscription.objects.select_for_update()
            .filter(public_id=subscription_public_id, staff_membership=membership)
            .first()
        )
        if subscription is None:
            raise PermissionDenied("Web Push subscription is not accessible")
        changed = subscription.is_active or any(
            (
                subscription.endpoint_ciphertext,
                subscription.p256dh_ciphertext,
                subscription.auth_ciphertext,
            )
        )
        if not changed:
            return False
        subscription.is_active = False
        subscription.disabled_at = timezone.now()
        subscription.endpoint_ciphertext = ""
        subscription.p256dh_ciphertext = ""
        subscription.auth_ciphertext = ""
        subscription.save(
            update_fields=(
                "is_active",
                "disabled_at",
                "endpoint_ciphertext",
                "p256dh_ciphertext",
                "auth_ciphertext",
                "updated_at",
            )
        )
        record_event(
            action="workshop_push.subscription_disabled",
            actor=actor,
            target=subscription,
            metadata={"source": self._safe_source(source)},
        )
        return changed

    @transaction.atomic
    def unsubscribe_all(self, *, actor, source: str) -> int:
        membership = self._require_workshop_access(actor)
        return self.disable_for_membership(
            staff_membership=membership,
            actor=actor,
            source=source,
        )

    @transaction.atomic
    def disable_for_membership(
        self,
        *,
        staff_membership: StaffMembership,
        actor,
        source: str,
    ) -> int:
        if getattr(
            actor, "pk", None
        ) != staff_membership.user_id and not self.access_service.can_manage_staff_team(actor):
            raise PermissionDenied("Workshop notification access denied")
        locked_membership = StaffMembership.objects.select_for_update().get(pk=staff_membership.pk)
        now = timezone.now()
        subscriptions = StaffPushSubscription.objects.filter(staff_membership=locked_membership)
        subscriptions = subscriptions.filter(
            Q(is_active=True)
            | ~Q(endpoint_ciphertext="")
            | ~Q(p256dh_ciphertext="")
            | ~Q(auth_ciphertext="")
        )
        count = subscriptions.update(
            is_active=False,
            disabled_at=now,
            endpoint_ciphertext="",
            p256dh_ciphertext="",
            auth_ciphertext="",
            updated_at=now,
        )
        if count:
            record_event(
                action="workshop_push.subscriptions_disabled",
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=locked_membership,
                metadata={"count": count, "source": self._safe_source(source)},
            )
        return count

    def read_recent_events(
        self,
        *,
        actor,
        cursor: UUID | str | None = None,
        limit: int = 20,
    ) -> WorkshopEventPage:
        self._require_workshop_access(actor)
        safe_limit = max(1, min(limit, settings.WEB_PUSH_POLL_MAX_EVENTS))
        queryset = WorkshopNotificationEvent.objects.order_by("created_at", "id")
        if not cursor:
            latest = WorkshopNotificationEvent.objects.order_by("-created_at", "-id").first()
            summaries = (
                (
                    WorkshopEventSummary(
                        public_id=str(latest.public_id),
                        event_type=latest.event_type,
                        created_at=latest.created_at.isoformat(),
                    ),
                )
                if latest
                else ()
            )
            return WorkshopEventPage(
                events=summaries,
                cursor=str(latest.public_id) if latest else None,
            )
        anchor = WorkshopNotificationEvent.objects.filter(public_id=cursor).first()
        if anchor is None:
            raise ValidationError("Unknown workshop event cursor")
        queryset = queryset.filter(
            Q(created_at__gt=anchor.created_at) | Q(created_at=anchor.created_at, id__gt=anchor.id)
        )
        events = list(queryset[:safe_limit])
        summaries = tuple(
            WorkshopEventSummary(
                public_id=str(event.public_id),
                event_type=event.event_type,
                created_at=event.created_at.isoformat(),
            )
            for event in events
        )
        next_cursor = str(events[-1].public_id) if events else (str(cursor) if cursor else None)
        return WorkshopEventPage(events=summaries, cursor=next_cursor)

    @transaction.atomic
    def publish_order_submitted(self, order, actor, source: str) -> WorkshopNotificationEvent:
        if order.status != order.Status.SUBMITTED:
            raise ValidationError("Only submitted orders can produce a workshop event")
        if order.customer_id is None:
            raise ValidationError("Workshop events require an order customer")
        event, created = WorkshopNotificationEvent.objects.get_or_create(
            event_type=WorkshopNotificationEvent.EventType.ORDER_SUBMITTED,
            order=order,
            defaults={
                "customer": order.customer,
                "actor": actor if getattr(actor, "is_authenticated", False) else None,
                "source": self._safe_source(source),
            },
        )
        if event.customer_id != order.customer_id:
            raise ValidationError("Workshop event tenant does not match its order")
        if created:
            record_event(
                action=WorkshopNotificationEvent.EventType.ORDER_SUBMITTED,
                actor=actor if getattr(actor, "is_authenticated", False) else None,
                target=event,
                metadata={
                    "customer_public_id": str(order.customer.public_id),
                    "order_public_id": str(order.public_id),
                    "source": self._safe_source(source),
                },
            )
            if settings.WEB_PUSH_ENABLED:
                event_public_id = str(event.public_id)
                transaction.on_commit(lambda: self._schedule_fanout(event_public_id))
        return event

    @transaction.atomic
    def fanout(self, *, event_public_id: UUID | str) -> int:
        if not settings.WEB_PUSH_ENABLED:
            return 0
        self._require_enabled_configuration()
        event = WorkshopNotificationEvent.objects.filter(public_id=event_public_id).first()
        if event is None:
            return 0
        now = timezone.now()
        subscriptions = list(
            StaffPushSubscription.objects.filter(
                is_active=True,
                staff_membership__is_active=True,
                staff_membership__user__is_active=True,
                staff_membership__user__is_staff=True,
            )
            .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
            .select_related("staff_membership__user")
        )
        eligible = [
            item
            for item in subscriptions
            if self._has_required_permissions(item.staff_membership.user)
        ]
        existing_ids = set(
            PushDelivery.objects.filter(event=event, subscription__in=eligible).values_list(
                "subscription_id", flat=True
            )
        )
        deliveries = [
            PushDelivery(event=event, subscription=subscription)
            for subscription in eligible
            if subscription.id not in existing_ids
        ]
        created = PushDelivery.objects.bulk_create(deliveries, ignore_conflicts=True)
        public_ids = [str(item.public_id) for item in created]
        if public_ids:
            transaction.on_commit(lambda: self._schedule_deliveries(public_ids))
        return len(created)

    def deliver(self, *, delivery_public_id: UUID | str) -> str:
        delivery = self._claim_delivery(delivery_public_id=delivery_public_id)
        if delivery is None:
            return "not_claimed"
        if not settings.WEB_PUSH_ENABLED:
            self._finish_delivery(
                delivery,
                status=PushDelivery.Status.SKIPPED,
                code="feature_disabled",
            )
            return PushDelivery.Status.SKIPPED
        subscription = delivery.subscription
        user = subscription.staff_membership.user
        if not subscription.is_active or (
            subscription.expires_at and subscription.expires_at <= timezone.now()
        ):
            self._finish_delivery(
                delivery,
                status=PushDelivery.Status.SKIPPED,
                code="subscription_inactive",
            )
            return PushDelivery.Status.SKIPPED
        if not subscription.staff_membership.is_active or not self._has_required_permissions(user):
            self._finish_delivery(
                delivery, status=PushDelivery.Status.SKIPPED, code="access_revoked"
            )
            return PushDelivery.Status.SKIPPED
        try:
            crypto = self._get_crypto()
            self._get_client().send(
                endpoint=crypto.decrypt(subscription.endpoint_ciphertext),
                p256dh=crypto.decrypt(subscription.p256dh_ciphertext),
                auth=crypto.decrypt(subscription.auth_ciphertext),
                payload={
                    "title": "Nouvelle commande Atelier",
                    "body": "Une nouvelle commande est disponible.",
                    "tag": f"workshop-{delivery.event.public_id}",
                    "url": "/staff/",
                    "event_public_id": str(delivery.event.public_id),
                },
            )
        except WebPushGone as exc:
            self._disable_gone_subscription(subscription, code=exc.code)
            self._finish_delivery(delivery, status=PushDelivery.Status.GONE, code=exc.code)
            self._audit_delivery_failure(
                delivery, action="workshop_push.subscription_gone", code=exc.code
            )
            return PushDelivery.Status.GONE
        except WebPushPermanentError as exc:
            self._register_subscription_failure(subscription, code=exc.code)
            self._finish_delivery(delivery, status=PushDelivery.Status.FAILED, code=exc.code)
            self._audit_delivery_failure(
                delivery, action="workshop_push.delivery_failed", code=exc.code
            )
            return PushDelivery.Status.FAILED
        except WebPushTransientError as exc:
            self._register_subscription_failure(subscription, code=exc.code)
            self._retry_delivery(delivery, code=exc.code)
            raise
        except Exception:
            self._register_subscription_failure(subscription, code="delivery_error")
            self._retry_delivery(delivery, code="delivery_error")
            unexpected_failure = True
        else:
            unexpected_failure = False

        if unexpected_failure:
            raise WebPushTransientError(code="delivery_error") from None

        now = timezone.now()
        PushDelivery.objects.filter(pk=delivery.pk, status=PushDelivery.Status.SENDING).update(
            status=PushDelivery.Status.SENT,
            delivered_at=now,
            claimed_at=None,
            next_attempt_at=None,
            failure_code="",
            updated_at=now,
        )
        StaffPushSubscription.objects.filter(pk=subscription.pk).update(
            consecutive_failures=0,
            last_failure_code="",
            updated_at=now,
        )
        return PushDelivery.Status.SENT

    @transaction.atomic
    def recover_stale_deliveries(self) -> int:
        if not settings.WEB_PUSH_ENABLED:
            return 0
        now = timezone.now()
        stale_before = now - timedelta(seconds=settings.WEB_PUSH_CLAIM_TIMEOUT_SECONDS)
        PushDelivery.objects.filter(
            status=PushDelivery.Status.SENDING,
            claimed_at__lt=stale_before,
        ).update(
            status=PushDelivery.Status.RETRY,
            claimed_at=None,
            next_attempt_at=now,
            failure_code="stale_claim",
            updated_at=now,
        )
        due = list(
            PushDelivery.objects.filter(
                status__in=(PushDelivery.Status.PENDING, PushDelivery.Status.RETRY),
            )
            .filter(Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now))
            .values_list("public_id", flat=True)[: settings.WEB_PUSH_RECOVERY_BATCH_SIZE]
        )
        public_ids = [str(item) for item in due]
        if public_ids:
            transaction.on_commit(lambda: self._schedule_deliveries(public_ids))
        return len(public_ids)

    def purge_history(self) -> tuple[int, int]:
        cutoff = timezone.now() - timedelta(days=settings.WEB_PUSH_RETENTION_DAYS)
        deleted_events, _ = WorkshopNotificationEvent.objects.filter(created_at__lt=cutoff).delete()
        deleted_subscriptions, _ = StaffPushSubscription.objects.filter(
            is_active=False,
            disabled_at__lt=cutoff,
        ).delete()
        return deleted_events, deleted_subscriptions

    def _claim_delivery(self, *, delivery_public_id: UUID | str) -> PushDelivery | None:
        now = timezone.now()
        with transaction.atomic():
            delivery = (
                PushDelivery.objects.select_for_update()
                .select_related("event", "subscription__staff_membership__user")
                .filter(public_id=delivery_public_id)
                .first()
            )
            if delivery is None or delivery.status not in {
                PushDelivery.Status.PENDING,
                PushDelivery.Status.RETRY,
            }:
                return None
            if delivery.next_attempt_at and delivery.next_attempt_at > now:
                return None
            delivery.status = PushDelivery.Status.SENDING
            delivery.claimed_at = now
            delivery.attempt_count += 1
            delivery.save(update_fields=("status", "claimed_at", "attempt_count", "updated_at"))
            return delivery

    @staticmethod
    def _finish_delivery(delivery: PushDelivery, *, status: str, code: str) -> None:
        now = timezone.now()
        PushDelivery.objects.filter(pk=delivery.pk).update(
            status=status,
            claimed_at=None,
            next_attempt_at=None,
            failure_code=code,
            updated_at=now,
        )

    def _retry_delivery(self, delivery: PushDelivery, *, code: str) -> None:
        now = timezone.now()
        if delivery.attempt_count >= settings.WEB_PUSH_MAX_ATTEMPTS:
            PushDelivery.objects.filter(pk=delivery.pk).update(
                status=PushDelivery.Status.FAILED,
                claimed_at=None,
                next_attempt_at=None,
                failure_code="retry_exhausted",
                updated_at=now,
            )
            self._audit_delivery_failure(
                delivery,
                action="workshop_push.delivery_retry_exhausted",
                code="retry_exhausted",
            )
            return
        delay = min(3600, 30 * (2 ** max(0, delivery.attempt_count - 1)))
        PushDelivery.objects.filter(pk=delivery.pk).update(
            status=PushDelivery.Status.RETRY,
            claimed_at=None,
            next_attempt_at=now + timedelta(seconds=delay),
            failure_code=code,
            updated_at=now,
        )

    @staticmethod
    def _register_subscription_failure(subscription: StaffPushSubscription, *, code: str) -> None:
        StaffPushSubscription.objects.filter(pk=subscription.pk).update(
            consecutive_failures=F("consecutive_failures") + 1,
            last_failure_code=code,
            updated_at=timezone.now(),
        )

    @staticmethod
    def _disable_gone_subscription(subscription: StaffPushSubscription, *, code: str) -> None:
        now = timezone.now()
        StaffPushSubscription.objects.filter(pk=subscription.pk).update(
            is_active=False,
            disabled_at=now,
            endpoint_ciphertext="",
            p256dh_ciphertext="",
            auth_ciphertext="",
            consecutive_failures=F("consecutive_failures") + 1,
            last_failure_code=code,
            updated_at=now,
        )

    @staticmethod
    def _audit_delivery_failure(delivery: PushDelivery, *, action: str, code: str) -> None:
        record_event(
            action=action,
            target=delivery,
            status="failure",
            metadata={"code": code},
        )

    def _require_workshop_access(self, actor) -> StaffMembership:
        membership = self.access_service.get_staff_membership(actor)
        if membership is None or not self._has_required_permissions(actor):
            raise PermissionDenied("Workshop notification access denied")
        return membership

    def _has_required_permissions(self, user) -> bool:
        return bool(
            self.access_service.can_access_staff_portal(user)
            and all(user.has_perm(permission) for permission in self.required_permissions)
        )

    def _configuration_is_valid(self) -> bool:
        if not settings.WEB_PUSH_ENABLED:
            return False
        try:
            self._require_enabled_configuration()
        except ImproperlyConfigured:
            return False
        return True

    def _require_enabled_configuration(self) -> None:
        if not settings.WEB_PUSH_ENABLED:
            raise WorkshopPushDisabled("Web Push is disabled")
        try:
            numeric_settings = (
                settings.WEB_PUSH_CLAIM_TIMEOUT_SECONDS,
                settings.WEB_PUSH_MAX_ATTEMPTS,
                settings.WEB_PUSH_MAX_ACTIVE_SUBSCRIPTIONS_PER_MEMBER,
                settings.WEB_PUSH_RECOVERY_BATCH_SIZE,
                settings.WEB_PUSH_RETENTION_DAYS,
                settings.WEB_PUSH_POLL_MAX_EVENTS,
            )
            if any(value <= 0 for value in numeric_settings):
                raise ImproperlyConfigured("Web Push limits must be positive")
            configuration = self._get_client().configuration
            configuration.validate()
            self._get_crypto()._require_keys()
        except ImproperlyConfigured as exc:
            raise WorkshopPushConfigurationError("Web Push is not configured") from exc

    def _get_crypto(self) -> PushSubscriptionCrypto:
        if self._crypto is None:
            self._crypto = PushSubscriptionCrypto()
        return self._crypto

    def _get_client(self) -> WebPushClient:
        if self._client is None:
            self._client = WebPushClient()
        return self._client

    @staticmethod
    def _safe_source(source: str) -> str:
        return (source or "unknown")[:64]

    @staticmethod
    def _schedule_fanout(event_public_id: str) -> None:
        from apps.notifications.tasks import fanout_workshop_notification_task

        fanout_workshop_notification_task.delay(event_public_id)

    @staticmethod
    def _schedule_deliveries(delivery_public_ids: list[str]) -> None:
        from apps.notifications.tasks import deliver_workshop_push_task

        for public_id in delivery_public_ids:
            deliver_workshop_push_task.delay(public_id)
