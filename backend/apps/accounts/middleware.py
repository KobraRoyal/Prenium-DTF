from __future__ import annotations

import ipaddress
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

from apps.auditlog.models import AuditLogEntry
from apps.auditlog.services import record_event

logger = logging.getLogger(__name__)


def _audit_ip(raw: str) -> str | None:
    try:
        return str(ipaddress.ip_address(raw.strip()))
    except ValueError:
        return None


def _client_ip(request):
    if getattr(settings, "LOGIN_RATE_LIMIT_TRUST_X_FORWARDED_FOR", False):
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        if xff:
            return xff.split(",")[0].strip()
    return request.META.get("HTTP_X_REAL_IP") or request.META.get("REMOTE_ADDR") or "0.0.0.0"


def _is_post_path(request, path: str) -> bool:
    if request.method != "POST":
        return False
    current = request.path.rstrip("/") or "/"
    return current == path.rstrip("/") or current == path


def _is_login_post(request) -> bool:
    return _is_post_path(request, "/login")


class LoginRateLimitMiddleware:
    """Limite les POST d'authentification par adresse IP (cache Django)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        blocked = self._blocked_response(request)
        if blocked is not None:
            return blocked
        return self.get_response(request)

    def _blocked_response(self, request):
        if _is_login_post(request):
            return self._enforce(
                request,
                cache_prefix="login_rl",
                max_attempts=getattr(settings, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 20),
                window=getattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900),
                action="security.login_rate_limited",
                log_event="login_rate_limited",
                message="Trop de tentatives de connexion. Réessayez plus tard.",
                audit_message="Limite de tentatives de connexion atteinte",
            )
        if _is_post_path(request, "/mot-de-passe-oublie"):
            return self._enforce(
                request,
                cache_prefix="pwd_reset_rl",
                max_attempts=getattr(settings, "PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS", 5),
                window=getattr(settings, "PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS", 3600),
                action="security.password_reset_rate_limited",
                log_event="password_reset_rate_limited",
                message="Trop de demandes de réinitialisation. Réessayez plus tard.",
                audit_message="Limite de demandes de réinitialisation atteinte",
            )
        return None

    def _enforce(
        self,
        request,
        *,
        cache_prefix: str,
        max_attempts: int,
        window: int,
        action: str,
        log_event: str,
        message: str,
        audit_message: str,
    ):
        ip = _client_ip(request)
        key = f"{cache_prefix}:{ip}"
        try:
            current = cache.incr(key)
        except ValueError:
            cache.add(key, 1, timeout=window)
            current = 1
        if current <= max_attempts:
            return None
        logger.warning(
            log_event,
            extra={"client_ip": ip, "attempts": current},
        )
        if current == max_attempts + 1:
            record_event(
                action=action,
                status=AuditLogEntry.Status.FAILURE,
                message=audit_message,
                ip_address=_audit_ip(ip),
                metadata={
                    "client_ip": ip,
                    "max_attempts": max_attempts,
                    "window_seconds": window,
                },
            )
        return HttpResponse(
            message,
            status=429,
            content_type="text/plain; charset=utf-8",
        )
