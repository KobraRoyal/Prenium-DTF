import pytest
from apps.auditlog.models import AuditLogEntry
from django.core.cache import cache
from django.test import Client
from django.test.utils import override_settings


@pytest.mark.django_db
@override_settings(
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS=3,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=3600,
)
def test_login_post_blocked_after_max_attempts():
    cache.clear()
    client = Client(enforce_csrf_checks=False)
    for _ in range(3):
        response = client.post("/login/", {"username": "nope", "password": "bad"})
        assert response.status_code != 429
    blocked = client.post("/login/", {"username": "nope", "password": "bad"})
    assert blocked.status_code == 429
    assert "Trop de tentatives" in blocked.content.decode()


@pytest.mark.django_db
@override_settings(
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS=3,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=3600,
)
def test_login_rate_limit_audit_once_per_window():
    cache.clear()
    client = Client(enforce_csrf_checks=False)
    for _ in range(3):
        client.post("/login/", {"username": "nope", "password": "bad"})
    assert client.post("/login/", {"username": "nope", "password": "bad"}).status_code == 429
    assert AuditLogEntry.objects.filter(action="security.login_rate_limited").count() == 1
    for _ in range(5):
        assert client.post("/login/", {"username": "nope", "password": "bad"}).status_code == 429
    assert AuditLogEntry.objects.filter(action="security.login_rate_limited").count() == 1
