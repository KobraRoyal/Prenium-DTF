from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
LANDING_DIR = ROOT_DIR / "backend" / "templates" / "shop"
PARTIALS_DIR = LANDING_DIR / "partials"
LANDING_CSS = ROOT_DIR / "backend" / "static_src" / "css" / "components" / "landing-conversion.css"
LANDING_MOTION = ROOT_DIR / "backend" / "static_src" / "js" / "landing-motion.js"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_services_page_uses_conversion_shell_and_preserves_service_copy() -> None:
    services = read(LANDING_DIR / "services.html")
    hero = read(PARTIALS_DIR / "services_hero.html")
    benefits = read(PARTIALS_DIR / "services_benefits.html")
    use_cases = read(PARTIALS_DIR / "services_use_cases.html")
    final_cta = read(PARTIALS_DIR / "services_cta_final.html")

    assert "landing-conversion-page" in services
    assert "services_hero.html" in services
    assert "services_benefits.html" in services
    assert "services_use_cases.html" in services
    assert "services_cta_final.html" in services
    assert "landing_footer.html" in services
    assert "agency-" not in services + hero + benefits + use_cases + final_cta
    assert "conversion-button conversion-button--primary" in hero
    assert "conversion-path conversion-path--production" in benefits
    assert "conversion-case conversion-case--wide" in use_cases
    assert "conversion-final" in final_cta


def test_home_keeps_one_landing_narrative_in_the_expected_order() -> None:
    home = read(LANDING_DIR / "home.html")
    partials = [
        "landing_hero.html",
        "landing_services.html",
        "landing_how_it_works.html",
        "landing_quality_proof.html",
        "landing_case_studies.html",
        "landing_faq.html",
        "landing_cta_final.html",
    ]

    positions = [home.index(partial) for partial in partials]

    assert positions == sorted(positions)
    assert "THESIS: Prenium DTF rend la production visible" in home
    assert "components/nav/landing_header.html" in home


def test_hero_has_two_actions_and_an_honestly_labelled_tracking_demo() -> None:
    hero = read(PARTIALS_DIR / "landing_hero.html")

    assert hero.count("conversion-button ") == 2
    assert hero.count("{% url 'prospects:step1' %}") == 1
    assert 'href="#landing-how-it-works"' in hero
    assert "Aperçu de démonstration" in hero
    assert "Production en cours" in hero
    assert "landing-eyebrow" not in hero
    assert "conversion-eyebrow" not in hero


def test_workflow_has_four_real_steps_without_repeating_the_conversion_cta() -> None:
    process = read(PARTIALS_DIR / "landing_how_it_works.html")

    assert process.count('class="conversion-flow__step"') == 4
    assert "Présentez votre activité" in process
    assert "Suivez l’atelier et l’envoi" in process
    assert "conversion-button" not in process
    assert "prospects:step1" not in process


def test_proof_cases_faq_and_final_cta_keep_product_truth() -> None:
    proof = read(PARTIALS_DIR / "landing_quality_proof.html")
    cases = read(PARTIALS_DIR / "landing_case_studies.html")
    faq = read(PARTIALS_DIR / "landing_faq.html")
    final_cta = read(PARTIALS_DIR / "landing_cta_final.html")

    assert "Chaque organisation n’accède qu’à ses propres données" in proof
    assert proof.count("<li>") == 3
    assert cases.count('class="conversion-case ') == 3
    assert faq.count("<details>") == 5
    assert "numéro de TVA intracommunautaire" in faq
    assert final_cta.count('class="conversion-button ') == 1
    assert "Présenter mon activité" in final_cta


def test_editorial_styles_use_the_locked_warm_light_palette_without_gradient() -> None:
    css = read(LANDING_CSS)
    editorial = css.split("/* Landing claire", 1)[1]

    assert "--landing-ivory: var(--bg)" in editorial
    assert "--landing-panel: var(--surface)" in editorial
    assert "--landing-ink: var(--ink)" in editorial
    assert "--landing-coral: var(--brand)" in editorial
    assert "--landing-purple: var(--accent)" in editorial
    assert "@layer utilities" in editorial
    assert "background-image: none" in editorial
    assert "border-radius: 2.25rem" in editorial
    assert "@media (max-width: 767px)" in editorial
    assert "grid-template-columns: minmax(0, 1fr)" in editorial
    assert "@media (prefers-reduced-motion: reduce)" in editorial


def test_landing_motion_keeps_progressive_enhancement_without_pointer_tilt() -> None:
    motion = read(LANDING_MOTION)

    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in motion
    assert "IntersectionObserver" in motion
    assert 'nodes.forEach((el) => el.classList.add("is-visible"))' in motion
    assert 'classList.add("js-landing-motion")' not in motion
    assert "initLandingBoardTilt" not in motion
    assert 'addEventListener("pointermove"' not in motion
