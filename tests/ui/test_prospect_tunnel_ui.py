import pytest
from apps.prospects.session import SESSION_KEY
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_prospect_steps_share_premium_structure_and_ctas():
    client = Client()

    step1 = client.get(reverse("prospects:step1"))
    assert step1.status_code == 200
    step1_html = step1.content.decode()
    assert "product-shell--prospect" in step1_html
    assert "prospect-shell__aside-card" in step1_html
    assert "data-submit-loading" in step1_html
    assert "ui-btn ui-btn-primary ui-btn-wide prospect-form__btn-primary" in step1_html

    session = client.session
    session[SESSION_KEY] = {
        "step1": {
            "first_name": "Jean",
            "last_name": "Martin",
            "email": "jean@example.com",
            "phone": "0102030405",
            "company": "Atelier Demo",
            "country": "FR",
            "activity_type": "brand",
        },
        "step2": {
            "service_interest": "dtf_transfer",
            "main_goal": "Tester la prod",
            "project_timing": "soon",
        },
        "step3": {
            "monthly_volume": "starter",
            "order_frequency": "monthly",
            "urgency": "normal",
        },
    }
    session.save()

    step2 = client.get(reverse("prospects:step2"))
    step3 = client.get(reverse("prospects:step3"))
    step4 = client.get(reverse("prospects:step4"))

    assert step2.status_code == 200
    assert step3.status_code == 200
    assert step4.status_code == 200

    step2_html = step2.content.decode()
    step3_html = step3.content.decode()
    step4_html = step4.content.decode()

    assert "prospect-tunnel__title" in step2_html
    assert "prospect-form__panel" in step2_html
    assert "Service recherché" in step2_html
    assert "Continuer" in step2_html
    assert "data-submit-loading" in step2_html
    assert "ui-btn ui-btn-secondary prospect-form__btn-secondary" in step2_html

    assert "prospect-tunnel__title" in step3_html
    assert "Volume mensuel" in step3_html
    assert "Fréquence" in step3_html
    assert "Urgence" in step3_html
    assert "data-submit-loading" in step3_html

    assert "prospect-tunnel__title" in step4_html
    assert "Accès sécurisé" in step4_html
    assert "Activer mon espace" in step4_html
    assert "data-submit-loading" in step4_html
