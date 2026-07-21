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
def test_user_can_update_personal_information_without_changing_login_email():
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
    assert "Mon compte" in html
    assert "account-profile-layout" in html
    assert "account-profile-rail" in html
    assert "Informations personnelles" in html
    assert "Connexion" in html
    assert 'x-on:input="dirty = true"' in html
    assert 'x-bind:disabled="!dirty"' in html
    assert 'name="first_name"' in html
    assert 'name="last_name"' in html
    assert 'name="email"' not in html
    assert user.email in html

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
