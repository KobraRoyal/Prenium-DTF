import re

import pytest
from apps.auditlog.models import AuditLogEntry
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.test.utils import override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


def _reset_url_from_mailbox() -> str:
    assert len(mail.outbox) == 1
    match = re.search(
        r"https://portal\.example\.test(/mot-de-passe-oublie/[^\s]+)",
        mail.outbox[0].body,
    )
    assert match is not None
    return match.group(1)


@pytest.mark.django_db
@override_settings(
    PUBLIC_BASE_URL="https://portal.example.test",
    SUPPORT_CONTACT_EMAIL="aide@prenium.example",
)
def test_login_page_exposes_password_reset_and_support():
    cache.clear()
    response = Client().get(reverse("portal:login"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Mot de passe oublié" in html
    assert reverse("portal:password-reset") in html
    assert "Besoin d'aide" in html
    assert "mailto:aide@prenium.example" in html


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_unknown_email_does_not_send_mail_and_uses_the_same_success_page(
    django_capture_on_commit_callbacks,
):
    cache.clear()
    client = Client()
    existing = get_user_model().objects.create_user(
        email="known@example.com",
        password="pass1234",
    )

    with django_capture_on_commit_callbacks(execute=True):
        missing = client.post(
            reverse("portal:password-reset"),
            {"email": "unknown@example.com"},
        )
        known = client.post(
            reverse("portal:password-reset"),
            {"email": existing.email},
        )

    assert missing.status_code == 302
    assert known.status_code == 302
    assert missing.url == known.url == reverse("portal:password-reset-done")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [existing.email]


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_inactive_or_unusable_password_accounts_do_not_receive_reset_mail():
    cache.clear()
    user_model = get_user_model()
    inactive = user_model.objects.create_user(
        email="inactive@example.com",
        password="pass1234",
        is_active=False,
    )
    unusable = user_model.objects.create_user(
        email="unusable@example.com",
        password="pass1234",
    )
    unusable.set_unusable_password()
    unusable.save(update_fields=["password"])

    client = Client()
    assert (
        client.post(
            reverse("portal:password-reset"),
            {"email": inactive.email},
        ).status_code
        == 302
    )
    assert (
        client.post(
            reverse("portal:password-reset"),
            {"email": unusable.email},
        ).status_code
        == 302
    )
    assert mail.outbox == []


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_reset_email_uses_public_id_and_completes_login_with_new_password(
    django_capture_on_commit_callbacks,
):
    cache.clear()
    user = get_user_model().objects.create_user(
        email="reset@example.com",
        password="OldPass1234",
        first_name="Camille",
    )
    client = Client()

    with django_capture_on_commit_callbacks(execute=True):
        request = client.post(reverse("portal:password-reset"), {"email": user.email})
    assert request.status_code == 302
    reset_path = _reset_url_from_mailbox()
    uidb64 = reset_path.strip("/").split("/")[1]
    decoded_uid = force_str(urlsafe_base64_decode(uidb64))
    assert decoded_uid == str(user.public_id)
    assert decoded_uid != str(user.pk)
    assert "/mot-de-passe-oublie/" in mail.outbox[0].body
    assert "https://portal.example.test/mot-de-passe-oublie/" in mail.outbox[0].body

    confirm = client.get(reset_path)
    assert confirm.status_code == 302
    assert confirm.url.endswith("/nouveau/")

    form_page = client.get(confirm.url)
    assert form_page.status_code == 200
    assert "Nouveau mot de passe" in form_page.content.decode()

    saved = client.post(
        confirm.url,
        {"new_password1": "NewStrongPass!234", "new_password2": "NewStrongPass!234"},
    )
    assert saved.status_code == 302
    assert saved.url == reverse("portal:password-reset-complete")
    user.refresh_from_db()
    assert user.check_password("NewStrongPass!234")
    assert AuditLogEntry.objects.filter(
        action="security.password_reset.completed",
        actor=user,
    ).exists()

    login_client = Client()
    assert login_client.login(email=user.email, password="NewStrongPass!234")


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_reset_token_cannot_be_reused_and_pk_uid_is_rejected(
    django_capture_on_commit_callbacks,
):
    cache.clear()
    user = get_user_model().objects.create_user(
        email="once@example.com",
        password="OldPass1234",
    )
    client = Client()
    with django_capture_on_commit_callbacks(execute=True):
        client.post(reverse("portal:password-reset"), {"email": user.email})
    reset_path = _reset_url_from_mailbox()

    first = client.get(reset_path)
    client.post(
        first.url,
        {"new_password1": "NewStrongPass!234", "new_password2": "NewStrongPass!234"},
    )

    reuse = Client().get(reset_path)
    assert reuse.status_code == 200
    assert "Lien invalide ou expiré" in reuse.content.decode()

    forged_uid = urlsafe_base64_encode(force_bytes(str(user.pk)))
    forged = Client().get(f"/mot-de-passe-oublie/{forged_uid}/not-a-token/")
    assert forged.status_code == 200
    assert "Lien invalide ou expiré" in forged.content.decode()


@pytest.mark.django_db
@override_settings(
    PUBLIC_BASE_URL="https://portal.example.test",
    PASSWORD_RESET_EMAIL_MAX_ATTEMPTS=1,
    PASSWORD_RESET_EMAIL_WINDOW_SECONDS=3600,
)
def test_per_email_throttle_hides_existence_and_stops_extra_mail(
    django_capture_on_commit_callbacks,
):
    cache.clear()
    user = get_user_model().objects.create_user(
        email="throttled@example.com",
        password="pass1234",
    )
    client = Client()
    with django_capture_on_commit_callbacks(execute=True):
        first = client.post(reverse("portal:password-reset"), {"email": user.email})
        second = client.post(reverse("portal:password-reset"), {"email": user.email})

    assert first.status_code == second.status_code == 302
    assert first.url == second.url
    assert len(mail.outbox) == 1
    audit = AuditLogEntry.objects.filter(action="security.password_reset.requested")
    assert audit.count() == 2
    assert audit.filter(metadata__throttled=True).count() == 1


@pytest.mark.django_db
@override_settings(
    PASSWORD_RESET_RATE_LIMIT_MAX_ATTEMPTS=2,
    PASSWORD_RESET_RATE_LIMIT_WINDOW_SECONDS=3600,
)
def test_password_reset_post_blocked_after_max_attempts():
    cache.clear()
    client = Client(enforce_csrf_checks=False)
    for _ in range(2):
        response = client.post(
            reverse("portal:password-reset"),
            {"email": "nope@example.com"},
        )
        assert response.status_code != 429
    blocked = client.post(
        reverse("portal:password-reset"),
        {"email": "nope@example.com"},
    )
    assert blocked.status_code == 429
    assert "Trop de demandes" in blocked.content.decode()
    assert AuditLogEntry.objects.filter(action="security.password_reset_rate_limited").count() == 1
