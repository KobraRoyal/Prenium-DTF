from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.auditlog.services import record_event
from apps.notifications.models import EmailTemplate, UserEmailNotificationMute
from apps.notifications.services.email_templates import EmailTemplateService

OPTIONAL_CLIENT_EMAIL_EVENTS = tuple(choice.value for choice in UserEmailNotificationMute.Event)



@dataclass(frozen=True)
class EmailNotificationChoice:
    event: str
    label: str
    enabled: bool


class UserEmailPreferenceService:
    def visible_choices(self, *, user) -> list[EmailNotificationChoice]:
        muted = set(
            UserEmailNotificationMute.objects.filter(user=user).values_list("event", flat=True)
        )
        sees_priced_notice = self._has_deferred_account(user)
        choices: list[EmailNotificationChoice] = []
        for event in OPTIONAL_CLIENT_EMAIL_EVENTS:
            if event == EmailTemplate.Event.ORDER_PRICED:
                if not sees_priced_notice:
                    continue
            else:
                template = email_template_service.get_effective_template(
                    event=event,
                    audience=EmailTemplate.Audience.CLIENT,
                )
                if not template.is_active:
                    continue
            choices.append(
                EmailNotificationChoice(
                    event=event,
                    label=str(EmailTemplate.Event(event).label),
                    enabled=event not in muted,
                )
            )
        return choices

    def _has_deferred_account(self, user) -> bool:
        from apps.customers.models import Customer, CustomerMembership

        return CustomerMembership.objects.filter(
            user=user,
            is_active=True,
            customer__is_active=True,
            customer__default_billing_mode=Customer.DefaultBillingMode.DEFERRED,
        ).exists()

    def deliverable_recipients(self, recipients: list[str], *, event: str) -> list[str]:
        emails = [item for item in recipients if str(item or "").strip()]
        if not emails or event not in OPTIONAL_CLIENT_EMAIL_EVENTS:
            return emails
        conditions = Q()
        for email in emails:
            conditions |= Q(user__email__iexact=email)
        muted = {
            email.casefold()
            for email in UserEmailNotificationMute.objects.filter(
                conditions,
                event=event,
            ).values_list("user__email", flat=True)
            if email
        }
        return [item for item in emails if item.casefold() not in muted]

    @transaction.atomic
    def replace_mutes(self, *, user, enabled_events, ip_address: str | None = None) -> None:
        get_user_model().objects.select_for_update().get(pk=user.pk)
        visible = {choice.event for choice in self.visible_choices(user=user)}
        enabled = {event for event in enabled_events if event in visible}
        muted = visible - enabled
        current = set(
            UserEmailNotificationMute.objects.filter(user=user, event__in=visible).values_list(
                "event", flat=True
            )
        )
        if current == muted:
            return
        UserEmailNotificationMute.objects.filter(user=user, event__in=visible).delete()
        UserEmailNotificationMute.objects.bulk_create(
            [UserEmailNotificationMute(user=user, event=event) for event in sorted(muted)]
        )
        record_event(
            action="notifications.email_preference.updated",
            actor=user,
            target=user,
            ip_address=ip_address,
            metadata={"muted_events": sorted(muted)},
        )


email_template_service = EmailTemplateService()
user_email_preference_service = UserEmailPreferenceService()
