from pathlib import Path

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
    assert "prospect-journey-page" in step1_html
    assert "prospect-journey__rail" in step1_html
    assert "prospect-shell__aside-card" in step1_html
    assert "prospect-journey__utility" not in step1_html
    assert "prospect-step1__proofs" not in step1_html
    assert "data-submit-loading" in step1_html
    assert "ui-btn ui-btn-primary ui-btn-wide prospect-form__btn-primary" in step1_html
    assert "prospect-step1__activity-grid" in step1_html
    assert 'role="radiogroup"' in step1_html
    assert "Votre entreprise" in step1_html
    assert "Continuer" in step1_html

    session = client.session
    session[SESSION_KEY] = {
        "step1": {
            "first_name": "Jean",
            "last_name": "Martin",
            "email": "jean@example.com",
            "phone": "0102030405",
            "company": "Atelier Demo",
            "country": "FR",
            "siren": "123456789",
            "vat_number": "",
            "activity_type": "brand",
        },
        "step2": {
            "service_interest": "dtf_meter",
            "main_goal": "Tester la prod",
            "project_timing": "ongoing",
            "monthly_volume": "10_50",
            "order_frequency": "monthly",
            "urgency": "medium",
        },
    }
    session.save()

    step2 = client.get(reverse("prospects:step2"))
    step3 = client.get(reverse("prospects:step3"))
    step4 = client.get(reverse("prospects:step4"))

    assert step2.status_code == 200
    assert step3.status_code == 200
    assert step4.status_code == 302
    assert step4.url == reverse("prospects:step3")

    step2_html = step2.content.decode()
    step3_html = step3.content.decode()
    assert "prospect-tunnel__title" in step2_html
    assert "prospect-project-section" in step2_html
    assert "prospect-project-options--services" in step2_html
    assert 'type="radio" name="service_interest"' in step2_html
    assert 'type="radio" name="monthly_volume"' in step2_html
    assert "Service qui vous intéresse" in step2_html
    assert "Voir le récapitulatif" in step2_html
    assert "data-submit-loading" in step2_html
    assert "ui-btn ui-btn-secondary prospect-form__btn-secondary" in step2_html

    assert "prospect-tunnel__title" in step3_html
    assert "prospect-review__grid" in step3_html
    assert "prospect-review__notice" not in step3_html
    assert "prospect-next-steps__heading" not in step3_html
    assert "Volume" in step3_html
    assert "Calendrier" in step3_html
    assert "data-submit-loading" in step3_html
    assert "Envoyer ma demande" in step3_html
    assert "France" in step3_html
    assert "DTF au mètre" in step3_html
    assert "10 à 50 mètres" in step3_html
    assert 'type="password"' not in step3_html


def test_prospect_step2_selected_service_card_keeps_readable_light_theme():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "entries"
        / "prospect.css"
    ).read_text()

    assert ".prospect-project-option:has(input:checked)" in css
    assert "background: color-mix(in srgb, var(--brand-soft) 72%, var(--surface)) !important;" in css
    assert ".prospect-project-option__copy strong" in css
    assert "color: var(--ink) !important;" in css
    assert "body.product-shell.prospect-journey-page" in css
    assert "--journey-lime: var(--brand-soft);" in css
    assert ".prospect-journey__progress-number span" in css
    assert "color: var(--muted) !important;" in css
    assert "outline: 3px solid var(--focus-ring) !important;" in css
    assert "@media (max-width: 767px)" in css
    assert ".prospect-project-options--compact" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css


def test_prospect_step3_review_keeps_light_shell_and_balanced_summary():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "entries"
        / "prospect.css"
    ).read_text()
    step3 = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "templates"
        / "prospects"
        / "step3.html"
    ).read_text()

    assert "body.product-shell.prospect-journey-page .prospect-review" in css
    assert "background: var(--surface-raised) !important;" in css
    assert "body.product-shell.prospect-journey-page .prospect-review__header" in css
    assert "body.product-shell.prospect-journey-page .prospect-review__header a" in css
    assert "body.product-shell.prospect-journey-page .prospect-consent-card" in css
    assert step3.count("prospect-review__item--wide") == 2
