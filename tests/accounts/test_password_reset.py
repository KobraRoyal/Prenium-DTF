import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode


@pytest.mark.django_db
@override_settings(PUBLIC_BASE_URL="https://portal.example.test")
def test_password_reset_sends_email_without_revealing_unknown_accounts():
    user = get_user_model().objects.create_user(email="reset@example.com", password="old-pass")
    client = Client()

    unknown = client.post(reverse("portal:password-reset"), {"email": "nobody@example.com"})
    assert unknown.status_code == 302
    assert unknown.url == reverse("portal:password-reset-done")
    assert mail.outbox == []

    known = client.post(reverse("portal:password-reset"), {"email": user.email})
    assert known.status_code == 302
    assert len(mail.outbox) == 1
    assert "https://portal.example.test" in mail.outbox[0].body
    assert "mot-de-passe-oublie" in mail.outbox[0].body

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    confirm_url = reverse(
        "portal:password-reset-confirm",
        kwargs={"uidb64": uid, "token": token},
    )
    session_redirect = client.get(confirm_url)
    assert session_redirect.status_code == 302
    confirm = client.post(
        session_redirect.url,
        {"new_password1": "NewStrongPass123", "new_password2": "NewStrongPass123"},
    )
    assert confirm.status_code == 302
    user.refresh_from_db()
    assert user.check_password("NewStrongPass123")
    assert client.login(email=user.email, password="NewStrongPass123")


@pytest.mark.django_db
def test_login_page_links_to_password_reset_without_internal_jargon():
    html = Client().get(reverse("portal:login")).content.decode()
    assert reverse("portal:password-reset") in html
    assert reverse("politique-confidentialite") in html
    assert "Mot de passe oublié" in html
    for forbidden in ["client", "staff", "backend", "permissions", "droits"]:
        assert forbidden not in html.lower()
