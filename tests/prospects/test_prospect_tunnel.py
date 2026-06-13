import pytest
from apps.prospects.models import ProspectProfile
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
def test_prospect_step1_requires_valid_email():
    client = Client()
    url = reverse("prospects:step1")
    response = client.post(
        url,
        {
            "first_name": "Jean",
            "last_name": "Test",
            "email": "pas-un-email",
            "phone": "0612345678",
            "company": "Studio T",
            "country": "FR",
            "activity_type": "creator",
        },
    )
    assert response.status_code == 200
    content = response.content.decode().lower()
    assert "email" in content and ("valide" in content or "valid" in content)


@pytest.mark.django_db
def test_prospect_tunnel_completes_and_creates_account():
    client = Client()
    email = "prospect.success@example.com"

    assert (
        client.post(
            reverse("prospects:step1"),
            {
                "first_name": "Jean",
                "last_name": "Ok",
                "email": email,
                "phone": "+33612345678",
                "company": "Marque OK",
                "country": "FR",
                "activity_type": "brand",
            },
        ).status_code
        == 302
    )

    assert (
        client.post(
            reverse("prospects:step2"),
            {
                "service_interest": "dtf_meter",
                "main_goal": "Lancer une capsule",
                "project_timing": "immediate",
            },
        ).status_code
        == 302
    )

    assert (
        client.post(
            reverse("prospects:step3"),
            {
                "monthly_volume": "10_50",
                "order_frequency": "monthly",
                "urgency": "medium",
            },
        ).status_code
        == 302
    )

    response = client.post(
        reverse("prospects:step4"),
        {
            "password": "ComplexPass-2026!",
            "password_confirm": "ComplexPass-2026!",
        },
    )
    assert response.status_code == 302
    assert response.url == reverse("prospects:confirmation")

    assert User.objects.filter(email__iexact=email).exists()
    user = User.objects.get(email__iexact=email)
    profile = ProspectProfile.objects.get(user=user)
    assert profile.status == ProspectProfile.Status.ACCOUNT_CREATED
    assert profile.company == "Marque OK"
    assert profile.customer is not None

    conf = client.get(reverse("prospects:confirmation"))
    assert conf.status_code == 200
    body = conf.content.decode()
    assert "Jean" in body
    assert "Bienvenue" in body


@pytest.mark.django_db
def test_prospect_step4_rejects_duplicate_email():
    User.objects.create_user(email="existing@example.com", password="pass")

    client = Client()
    email = "existing@example.com"
    for step, data in [
        (
            "prospects:step1",
            {
                "first_name": "A",
                "last_name": "B",
                "email": email,
                "phone": "0600000000",
                "company": "Co",
                "country": "FR",
                "activity_type": "other",
            },
        ),
        (
            "prospects:step2",
            {
                "service_interest": "unsure",
                "project_timing": "exploring",
            },
        ),
        (
            "prospects:step3",
            {
                "monthly_volume": "lt10",
                "order_frequency": "punctual",
                "urgency": "low",
            },
        ),
    ]:
        r = client.post(reverse(step), data)
        assert r.status_code == 302, step

    response = client.post(
        reverse("prospects:step4"),
        {
            "password": "Another-Complex-2026!",
            "password_confirm": "Another-Complex-2026!",
        },
    )
    assert response.status_code == 200
    assert "existe" in response.content.decode().lower()


@pytest.mark.django_db
def test_prospect_step2_redirects_without_step1():
    client = Client()
    response = client.get(reverse("prospects:step2"))
    assert response.status_code == 302
    assert response.url == reverse("prospects:step1")


@pytest.mark.django_db
def test_portal_login_still_accessible():
    client = Client()
    r = client.get(reverse("portal:login"))
    assert r.status_code == 200


@pytest.mark.django_db
def test_prospect_urls_use_demande_acces_and_legacy_redirects():
    assert reverse("prospects:step1") == "/demande-acces/etape-1/"
    client = Client()
    r = client.get("/compte-pro/etape-1/", follow=False)
    assert r.status_code == 301
    assert r["Location"] == "/demande-acces/etape-1/"
