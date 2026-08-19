import pytest
from apps.accounts.services.email_change import EmailChangeService
from apps.auditlog.models import AuditLogEntry
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import Client, override_settings
from django.urls import reverse


def _token_from_mailbox() -> str:
    body = mail.outbox[0].body
    marker = "email-change/confirmer/"
    assert marker in body
    return body.split(marker, 1)[1].split()[0].rstrip("/")


def _login(email: str) -> tuple[object, object]:
    user = get_user_model().objects.create_user(email=email, password="pass")
    client = Client()
    assert client.login(email=user.email, password="pass")
    return user, client


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_email_change_sends_link_to_new_address_and_confirms():
    user, client = _login("current@example.com")

    response = client.post(
        reverse("portal:email-change"),
        {"new_email": "nouveau@example.com", "space": "client"},
    )
    assert response.status_code == 302
    assert "sent=1" in response.url
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["nouveau@example.com"]
    assert "https://portal.example.test" in mail.outbox[0].body
    assert "email-change/confirmer" in mail.outbox[0].body
    user.refresh_from_db()
    assert user.email == "current@example.com"

    token = _token_from_mailbox()
    confirm = client.get(reverse("portal:email-change-confirm", kwargs={"token": token}))
    assert confirm.status_code == 302
    assert "email_changed=1" in confirm.url
    user.refresh_from_db()
    assert user.email == "nouveau@example.com"
    assert AuditLogEntry.objects.filter(action="account.email_change.confirmed").exists()
    assert client.login(email="nouveau@example.com", password="pass")


@pytest.mark.django_db
def test_email_change_rejects_address_already_used_by_another_account():
    get_user_model().objects.create_user(email="taken@example.com", password="pass")
    _user, client = _login("owner@example.com")

    response = client.post(reverse("portal:email-change"), {"new_email": "taken@example.com"})
    assert response.status_code == 400
    assert "déjà utilisée" in response.content.decode()
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_email_change_token_cannot_be_used_by_another_logged_in_user():
    owner, owner_client = _login("owner-a@example.com")
    owner_client.post(reverse("portal:email-change"), {"new_email": "next-a@example.com"})
    token = _token_from_mailbox()

    _intruder, other_client = _login("owner-b@example.com")
    stolen = other_client.get(reverse("portal:email-change-confirm", kwargs={"token": token}))
    assert stolen.status_code == 400
    owner.refresh_from_db()
    assert owner.email == "owner-a@example.com"


@pytest.mark.django_db
def test_email_change_rejects_invalid_token():
    _user, client = _login("token@example.com")
    response = client.get(
        reverse("portal:email-change-confirm", kwargs={"token": "not-a-valid-token"})
    )
    assert response.status_code == 400
    assert "plus valable" in response.content.decode()


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_email_change_token_is_invalidated_after_password_change():
    user, client = _login("rotate@example.com")
    client.post(reverse("portal:email-change"), {"new_email": "rotate-new@example.com"})
    token = _token_from_mailbox()
    user.set_password("NewStrongPass123")
    user.save(update_fields=["password"])
    client.login(email="rotate@example.com", password="NewStrongPass123")
    response = client.get(reverse("portal:email-change-confirm", kwargs={"token": token}))
    assert response.status_code == 400
    user.refresh_from_db()
    assert user.email == "rotate@example.com"


@pytest.mark.django_db
@override_settings(
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS=3,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS=3600,
)
def test_email_change_post_is_rate_limited_by_ip():
    cache.clear()
    _user, client = _login("rate@example.com")
    for index in range(3):
        response = client.post(
            reverse("portal:email-change"),
            {"new_email": f"rate-{index}@example.net"},
        )
        assert response.status_code != 429
    blocked = client.post(
        reverse("portal:email-change"),
        {"new_email": "rate-blocked@example.net"},
    )
    assert blocked.status_code == 429


@pytest.mark.django_db
def test_email_change_requires_authentication():
    response = Client().get(reverse("portal:email-change"))
    assert response.status_code == 302
    assert reverse("portal:login") in response.url


@pytest.mark.django_db
def test_email_change_service_rate_limit_per_user():
    cache.clear()
    user = get_user_model().objects.create_user(email="burst@example.com", password="pass")
    service = EmailChangeService()
    with override_settings(EMAIL_CHANGE_RATE_LIMIT_MAX_ATTEMPTS=1):
        service.request_change(user=user, new_email="burst-1@example.net")
        with pytest.raises(ValidationError, match="Trop de demandes"):
            service.request_change(user=user, new_email="burst-2@example.net")
