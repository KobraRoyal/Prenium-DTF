from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from django.db import models

from apps.auditlog.services import record_event


def get_request_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def normalize_audit_value(value):
    if isinstance(value, UUID):
        return str(value)

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, models.Model):
        public_id = getattr(value, "public_id", None)
        return {
            "model": value.__class__.__name__,
            "public_id": str(public_id) if public_id is not None else None,
            "repr": str(value),
        }

    if hasattr(value, "all"):
        values = [normalize_audit_value(item) for item in value.all()]
        return sorted(values, key=str)

    if isinstance(value, list | tuple | set):
        return [normalize_audit_value(item) for item in value]

    return value


class AdminAuditMixin:
    audit_create_action = ""
    audit_update_action = ""
    audit_delete_action = ""
    audit_fields: tuple[str, ...] = ()

    def get_audit_snapshot(self, obj) -> dict[str, object]:
        return {
            field_name: normalize_audit_value(getattr(obj, field_name))
            for field_name in self.audit_fields
        }

    def get_audit_changes(
        self, before: dict[str, object] | None, after: dict[str, object]
    ) -> dict[str, dict[str, object]]:
        if before is None:
            return {field: {"after": value} for field, value in after.items()}

        changes = {}
        for field, value in after.items():
            previous = before.get(field)
            if previous != value:
                changes[field] = {
                    "before": previous,
                    "after": value,
                }
        return changes

    def record_admin_event(
        self, request, *, action: str, target, changes: dict[str, object]
    ) -> None:
        if not action:
            return

        record_event(
            action=action,
            actor=request.user,
            target=target,
            ip_address=get_request_ip(request),
            metadata={
                "source": "django_admin",
                "path": request.path,
                "changes": changes,
            },
        )

    def save_model(self, request, obj, form, change):
        obj._audit_before_snapshot = None
        obj._audit_is_create = not change

        if change and obj.pk:
            obj._audit_before_snapshot = self.get_audit_snapshot(self.model.objects.get(pk=obj.pk))

        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        obj = form.instance
        after_snapshot = self.get_audit_snapshot(obj)
        before_snapshot = getattr(obj, "_audit_before_snapshot", None)

        if getattr(obj, "_audit_is_create", False):
            self.record_admin_event(
                request,
                action=self.audit_create_action,
                target=obj,
                changes=self.get_audit_changes(None, after_snapshot),
            )
            return

        changes = self.get_audit_changes(before_snapshot, after_snapshot)
        if changes:
            self.record_admin_event(
                request,
                action=self.audit_update_action,
                target=obj,
                changes=changes,
            )

    def delete_model(self, request, obj):
        self.record_admin_event(
            request,
            action=self.audit_delete_action,
            target=obj,
            changes=self.get_audit_snapshot(obj),
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            self.record_admin_event(
                request,
                action=self.audit_delete_action,
                target=obj,
                changes=self.get_audit_snapshot(obj),
            )
        super().delete_queryset(request, queryset)
