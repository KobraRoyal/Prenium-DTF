from __future__ import annotations

import re

from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.services.access import AccessScopeService
from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
SKU_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,78}$")
LOCATION_CODE_RE = re.compile(r"^[A-Z0-9]{1,8}(-[A-Z0-9]{1,8}){1,5}$")


def require_staff_perm(actor, permission: str, *, source: str, action: str) -> None:
    access = AccessScopeService()
    if not access.can_access_staff_portal(actor) or not actor.has_perm(permission):
        record_event(
            action=action,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            status=AuditLogEntry.Status.FAILURE,
            message="Permission POD/WMS refusée.",
            metadata={"source": source, "permission": permission},
        )
        raise PermissionDenied


def clean_sku(value: str, *, field_label: str = "SKU") -> str:
    sku = (value or "").strip().upper()
    if not SKU_RE.match(sku):
        raise ValidationError(f"{field_label} invalide (lettres, chiffres, . _ -).")
    return sku


def clean_location_code(value: str) -> str:
    code = (value or "").strip().upper()
    if not LOCATION_CODE_RE.match(code):
        raise ValidationError("Code emplacement invalide (ex. A-03-02-B).")
    return code


def clean_hex_color(value: str) -> str:
    color = (value or "").strip()
    if not color:
        return ""
    if not color.startswith("#"):
        color = f"#{color}"
    if not HEX_COLOR_RE.match(color):
        raise ValidationError("Couleur hex invalide (ex. #1A2B3C).")
    return color.upper()


def validation_message(exc: ValidationError) -> str:
    if hasattr(exc, "messages"):
        return " ".join(str(item) for item in exc.messages)
    return str(exc)
