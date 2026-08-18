import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_legal_pages_are_public_and_describe_the_controller():
    client = Client()
    pages = {
        "mentions-legales": "Mentions légales",
        "politique-confidentialite": "Politique de confidentialité",
        "politique-cookies": "Cookies",
        "accord-sous-traitance": "Accord de sous-traitance",
    }
    for name, heading in pages.items():
        response = client.get(reverse(name))
        assert response.status_code == 200
        html = response.content.decode()
        assert heading in html
        assert "IDS Supply" in html
        assert reverse("politique-confidentialite") in html or name == "politique-confidentialite"


@pytest.mark.django_db
def test_privacy_policy_stays_reachable_when_home_redirects_to_login(monkeypatch):
    monkeypatch.setenv("MARKETING_HOME_REDIRECT_TO_LOGIN", "1")
    client = Client()
    assert client.get(reverse("home")).status_code == 302
    response = client.get(reverse("politique-confidentialite"))
    assert response.status_code == 200
    assert "RGPD" in response.content.decode()
    assert reverse("portal:email-change") in response.content.decode()


@pytest.mark.django_db
def test_landing_footer_exposes_legal_links():
    html = Client().get(reverse("home")).content.decode()
    assert reverse("mentions-legales") in html
    assert reverse("politique-confidentialite") in html
    assert reverse("politique-cookies") in html
    assert reverse("accord-sous-traitance") in html
