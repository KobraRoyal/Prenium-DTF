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


def _is_login_post(request) -> bool:
    if request.method != "POST":
        return False
    path = request.path.rstrip("/") or "/"
    return path == "/login"


class LoginRateLimitMiddleware:
    """Limite les POST sur /login/ par adresse IP (cache Django)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if _is_login_post(request):
            max_attempts = getattr(settings, "LOGIN_RATE_LIMIT_MAX_ATTEMPTS", 20)
            window = getattr(settings, "LOGIN_RATE_LIMIT_WINDOW_SECONDS", 900)
            ip = _client_ip(request)
            key = f"login_rl:{ip}"
            try:
                current = cache.incr(key)
            except ValueError:
                cache.add(key, 1, timeout=window)
                current = 1
            if current > max_attempts:
                logger.warning(
                    "login_rate_limited",
                    extra={"client_ip": ip, "attempts": current},
                )
                if current == max_attempts + 1:
                    record_event(
                        action="security.login_rate_limited",
                        status=AuditLogEntry.Status.FAILURE,
                        message="Limite de tentatives de connexion atteinte",
                        ip_address=_audit_ip(ip),
                        metadata={
                            "client_ip": ip,
                            "max_attempts": max_attempts,
                            "window_seconds": window,
                        },
                    )
                return HttpResponse(
                    "Trop de tentatives de connexion. Réessayez plus tard.",
                    status=429,
                    content_type="text/plain; charset=utf-8",
                )
        return self.get_response(request)
