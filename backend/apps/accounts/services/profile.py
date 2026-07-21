from __future__ import annotations

from django.db import transaction

from apps.accounts.models import User
from apps.auditlog.services import record_event


class AccountProfileService:
    @transaction.atomic
    def update_personal_information(
        self,
        *,
        user: User,
        first_name: str,
        last_name: str,
    ) -> User:
        locked = User.objects.select_for_update().get(pk=user.pk)
        values = {
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
        }
        changed_fields = [
            field_name
            for field_name, value in values.items()
            if getattr(locked, field_name) != value
        ]
        if not changed_fields:
            return locked

        for field_name in changed_fields:
            setattr(locked, field_name, values[field_name])
        locked.save(update_fields=[*changed_fields, "updated_at"])
        record_event(
            action="account.profile.updated",
            actor=locked,
            target=locked,
            metadata={"fields": changed_fields},
        )
        return locked
