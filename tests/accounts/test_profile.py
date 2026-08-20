import pytest
from apps.auditlog.models import AuditLogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_profile_page_requires_authentication():
    response = Client().get(reverse("portal:profile"))

    assert response.status_code == 302
    assert reverse("portal:login") in response.url


@pytest.mark.django_db
def test_profile_page_shows_identity_display_instead_of_inline_form():
    user = get_user_model().objects.create_user(
        email="profile@example.com",
        password="pass",
        first_name="Ancien",
        last_name="Nom",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    page = client.get(f"{reverse('portal:profile')}?space=client")

    assert page.status_code == 200
    html = page.content.decode()
    assert "Mes informations" in html
    assert "account-profile-layout" in html
    assert "account-profile-rail" in html
    assert "Identité" in html
    assert "Ancien" in html
    assert "Nom" in html
    assert "E-mail de connexion" in html
    assert "Pour le modifier, contactez l’atelier." in html
    assert "Modifier" in html
    assert reverse("portal:profile-identity") in html
    assert "Verrouillé" not in html
    assert 'href="#connection-email"' not in html
    assert "Modifiez un champ pour activer l’enregistrement." not in html
    assert 'x-on:input="dirty = true"' not in html
    assert 'x-bind:disabled="!dirty"' not in html
    assert 'name="first_name"' not in html
    assert 'name="last_name"' not in html
    assert 'name="email"' not in html
    assert user.email in html


@pytest.mark.django_db
def test_user_can_update_personal_information_without_changing_login_email():
    user = get_user_model().objects.create_user(
        email="profile@example.com",
        password="pass",
        first_name="Ancien",
        last_name="Nom",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.post(
        reverse("portal:profile"),
        {
            "space": "client",
            "first_name": "Camille",
            "last_name": "Martin",
            "email": "attacker@example.com",
        },
    )

    assert response.status_code == 302
    assert response.url.endswith("?space=client&saved=1")
    user.refresh_from_db()
    assert user.first_name == "Camille"
    assert user.last_name == "Martin"
    assert user.email == "profile@example.com"
    audit = AuditLogEntry.objects.get(action="account.profile.updated", actor=user)
    assert set(audit.metadata["fields"]) == {"first_name", "last_name"}
    assert "Camille" not in str(audit.metadata)

    confirmation = client.get(response.url)
    assert confirmation.status_code == 200
    assert "Vos informations ont été enregistrées." in confirmation.content.decode()
    assert "Camille" in confirmation.content.decode()
    assert "Martin" in confirmation.content.decode()


@pytest.mark.django_db
def test_user_can_update_identity_via_htmx():
    user = get_user_model().objects.create_user(
        email="identity-htmx@example.com",
        password="pass",
        first_name="Ancien",
        last_name="Nom",
    )
    client = Client()
    assert client.login(email=user.email, password="pass")
    url = reverse("portal:profile-identity")

    redirect = client.get(f"{url}?space=client")
    assert redirect.status_code == 302
    assert redirect.url.endswith("?space=client")

    form = client.get(f"{url}?edit=1&space=client", HTTP_HX_REQUEST="true")
    assert form.status_code == 200
    form_html = form.content.decode()
    assert 'name="first_name"' in form_html
    assert 'name="last_name"' in form_html
    assert 'id="id_login_email"' in form_html
    assert "readonly" in form_html
    assert "autofocus" in form_html
    assert 'name="email"' not in form_html

    response = client.post(
        url,
        {
            "space": "client",
            "first_name": "Camille",
            "last_name": "Martin",
            "email": "attacker@example.com",
        },
        HTTP_HX_REQUEST="true",
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "Camille" in html
    assert "Martin" in html
    assert "Modifier" in html
    assert 'name="first_name"' not in html
    assert 'id="account-profile-rail-name"' in html
    assert "hx-swap-oob" in html
    assert "X-Prenium-Toast" in response.headers
    user.refresh_from_db()
    assert user.first_name == "Camille"
    assert user.last_name == "Martin"
    assert user.email == "identity-htmx@example.com"
    audit = AuditLogEntry.objects.get(action="account.profile.updated", actor=user)
    assert set(audit.metadata["fields"]) == {"first_name", "last_name"}
    assert "Camille" not in str(audit.metadata)


@pytest.mark.django_db
def test_profile_page_preserves_authorized_staff_navigation():
    user = get_user_model().objects.create_user(
        email="profile-staff@example.com",
        password="pass",
        is_staff=True,
    )
    user.user_permissions.add(Permission.objects.get(codename="access_staff_portal"))
    client = Client()
    assert client.login(email=user.email, password="pass")

    response = client.get(f"{reverse('portal:profile')}?space=staff")

    assert response.status_code == 200
    html = response.content.decode()
    assert "Atelier" in html
    assert "Dashboard" in html
    assert "Mon compte" in html
    assert "Identité" in html
    assert reverse("portal:profile-identity") in html
    assert "space=staff" in html
