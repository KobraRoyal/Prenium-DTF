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
    assert "prospect-journey__topbar" in step1_html
    assert "prospect-journey__breadcrumb" in step1_html
    assert 'aria-label="Fil d’Ariane de la demande d’accès"' in step1_html
    assert "prospect-stepper__connector" in step1_html
    assert "Demande d’accès professionnel" in step1_html
    assert "Deux étapes pour ouvrir votre compte professionnel." in step1_html
    assert "Accès professionnel" in step1_html
    assert "Votre compte" in step1_html
    assert "prospect-journey__rail" not in step1_html
    assert "prospect-journey__progress" not in step1_html
    assert "prospect-tunnel__track" not in step1_html
    assert "Votre progression" not in step1_html
    assert "prospect-journey__utility" not in step1_html
    assert "prospect-step1__proofs" not in step1_html
    assert "data-submit-loading" in step1_html
    assert "data-prospect-error-recovery" in step1_html
    assert "ui-btn ui-btn-primary ui-btn-wide prospect-form__btn-primary" in step1_html
    assert "prospect-step1__activity-grid" in step1_html
    assert 'role="radiogroup"' in step1_html
    assert "prospect-step1__activity-marker" in step1_html
    assert "Votre entreprise" in step1_html
    assert 'name="billing_address_line1"' in step1_html
    assert 'autocomplete="address-line1"' in step1_html
    assert 'name="billing_postal_code"' in step1_html
    assert 'name="billing_city"' in step1_html
    assert "Adresse professionnelle" in step1_html
    assert "Continuer" in step1_html
    assert "adresse professionnelle et identifiant d’entreprise" in step1_html

    journey_css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "components"
        / "prospect-journey.css"
    ).read_text()
    breadcrumb_rule = journey_css.split(
        "body.prospect-journey-page .prospect-journey__breadcrumb", 1
    )[1].split("}", 1)[0]
    assert "position: sticky;" in breadcrumb_rule
    assert "top: var(--journey-sticky-top);" in breadcrumb_rule
    assert "background: var(--journey-paper);" in breadcrumb_rule

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
    assert step3.status_code == 302
    assert step3.url == reverse("prospects:step2")
    assert step4.status_code == 302
    assert step4.url == reverse("prospects:step2")

    step2_html = step2.content.decode()
    assert "prospect-tunnel__title" in step2_html
    assert "prospect-project-section" in step2_html
    assert "prospect-project-options--services" not in step2_html
    assert 'type="radio" name="service_interest"' not in step2_html
    assert 'type="radio" name="monthly_volume"' in step2_html
    assert "prospect-project-option__marker" in step2_html
    assert step2_html.count('type="radio"') == step2_html.count("prospect-project-option__marker")
    assert "prospect-project-option__check" not in step2_html
    assert "Service qui vous intéresse" not in step2_html
    assert "prospect-confirmation" in step2_html
    assert "Je confirme l’exactitude des informations saisies." in step2_html
    assert 'name="terms_accepted"' in step2_html
    assert "Envoyer ma demande" in step2_html
    assert "e-mail de vérification valable 48 heures" in step2_html
    assert "Situez simplement votre projet" in step2_html
    assert "data-submit-loading" in step2_html
    assert "data-prospect-error-recovery" in step2_html
    assert "ui-btn ui-btn-secondary prospect-form__btn-secondary" in step2_html
    assert "Passer à la confirmation" not in step2_html


def test_prospect_step2_options_keep_readable_light_theme():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "entries"
        / "prospect.css"
    ).read_text()

    assert ".prospect-project-option:has(input:checked)" in css
    assert (
        "background: color-mix(in srgb, var(--brand-soft) 72%, var(--surface)) !important;" in css
    )
    assert ".prospect-project-option__copy strong" in css
    assert "color: var(--ink) !important;" in css
    assert "body.product-shell.prospect-journey-page" in css
    assert "--journey-lime: var(--brand-soft);" in css
    assert "min-height: 2.75rem;" in css
    assert "padding: 0.65rem 0.85rem;" in css
    assert "border-color: var(--focus-ring);" in css
    assert "outline: 3px solid var(--focus-ring) !important;" in css
    assert "@media (max-width: 767px)" in css
    assert ".prospect-project-options--compact" in css
    assert "grid-template-columns: minmax(0, 1fr);" in css


def test_prospect_desktop_header_is_compact_without_changing_mobile_layout():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "components"
        / "prospect-journey.css"
    ).read_text()

    desktop_rules = css.split("@media (min-width: 768px)", 1)[1].split("/* Sections */", 1)[0]

    assert "body.prospect-journey-page .prospect-journey__topbar" in desktop_rules
    assert "display: flex;" in desktop_rules
    assert "padding: 0.8rem 0 0.7rem;" in desktop_rules
    assert "body.prospect-journey-page .prospect-stepper" in desktop_rules
    assert "padding: 0.6rem 0;" in desktop_rules
    assert "padding-top: clamp(1.25rem, 2vw, 1.75rem);" in desktop_rules


def test_prospect_shell_avoids_a_full_white_frame():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "entries"
        / "prospect.css"
    ).read_text()

    frame_rule = css.split("body.prospect-journey-page .prospect-journey__frame", 1)[1].split(
        "}", 1
    )[0]
    shell_rows = css.split("body.prospect-journey-page .prospect-journey__topbar", 1)[1].split(
        "}", 1
    )[0]

    assert "border: 0;" in frame_rule
    assert "background: transparent;" in frame_rule
    assert "box-shadow: none !important;" in frame_rule
    assert "background: transparent;" in shell_rows

    assert "body.product-shell.prospect-journey-page .prospect-form__footer" in css
    assert "background: transparent !important;" in css
    assert "box-shadow: none !important;" in css


def test_prospect_journey_keeps_the_context_minimal_and_centers_the_progress():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "entries"
        / "prospect.css"
    ).read_text()

    minimal_rules = css.split(
        "Parcours : contexte concis, sans surface additionnelle avant la saisie.", 1
    )[1]

    assert "--journey-shell-max: 52rem;" in minimal_rules
    assert "background: transparent;" in minimal_rules
    assert "box-shadow: none;" in minimal_rules
    assert "width: min(100%, 32rem);" in minimal_rules
    assert "margin-inline: auto;" in minimal_rules
    assert "prospect-stepper__item.is-current" in minimal_rules
    assert "prospect-step1__section" in css
    assert "box-shadow: var(--shadow-soft);" in css


def test_prospect_form_sections_do_not_stack_two_surface_frames():
    root = Path(__file__).resolve().parents[2] / "backend"
    journey_css = (root / "static_src" / "css" / "entries" / "prospect.css").read_text()
    polish_css = (root / "static_src" / "css" / "components" / "product-polish.css").read_text()

    section_surface_rule = journey_css.split(
        "body.prospect-journey-page .prospect-step1__section,", 1
    )[1].split("}", 1)[0]
    assert ".prospect-confirmation" not in section_surface_rule
    assert ".prospect-step1__surface" not in polish_css


def test_prospect_header_uses_the_same_brand_and_account_structure_as_portals():
    root = Path(__file__).resolve().parents[2] / "backend"
    tunnel = (root / "templates" / "prospects" / "base_tunnel.html").read_text()
    header = (root / "templates" / "components" / "nav" / "landing_header.html").read_text()

    assert 'with header_mode="prospect"' in tunnel
    assert "Accès professionnel" in header
    assert '<span class="product-nav__section-label">Votre compte</span>' in header
    assert '{% if header_mode == "prospect" %}' in header


def test_prospect_confirmation_is_inline_and_keeps_a_single_clear_action():
    css = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "static_src"
        / "css"
        / "entries"
        / "prospect.css"
    ).read_text()
    step2 = (
        Path(__file__).resolve().parents[2] / "backend" / "templates" / "prospects" / "step2.html"
    ).read_text()

    assert "body.product-shell.prospect-journey-page .prospect-consent-card" in css
    assert "prospect-confirmation--inline" in step2
    assert "prospect-consent-card" in step2
    assert "prospect-review" not in step2
    assert "Récapitulatif" not in step2


def test_prospect_forms_recover_focus_after_server_validation_errors():
    runtime = (
        Path(__file__).resolve().parents[2] / "backend" / "static_src" / "js" / "product-shell.js"
    ).read_text()

    assert "function initProspectErrorRecovery()" in runtime
    assert "form[data-prospect-error-recovery]" in runtime
    assert "form.querySelector(\"[aria-invalid='true']\")" in runtime
    assert "firstInvalid.focus({ preventScroll: true });" in runtime
    assert "prefers-reduced-motion" in runtime


def test_prospect_forms_show_inline_required_errors_before_server_submission():
    root = Path(__file__).resolve().parents[2] / "backend"
    templates = root / "templates" / "prospects"
    runtime = (root / "static_src" / "js" / "product-shell.js").read_text()

    for filename in ("step1.html", "step2.html", "step3.html"):
        template = (templates / filename).read_text()
        assert "data-inline-required" in template
        assert 'class="ui-field-error ui-error-text"' in template

    step1 = (templates / "step1.html").read_text()
    step2 = (templates / "step2.html").read_text()
    assert 'aria-describedby="first-name-error"' in step1
    assert 'aria-describedby="activity-type-error"' in step1
    assert 'aria-describedby="project-timing-error"' in step2
    assert 'aria-describedby="terms-accepted-error"' in step2
    assert "function inlineRequiredRadioGroupLeader(field)" in runtime
    assert "inlineRequiredFieldFromEvent(event.target)" in runtime
