from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from apps.catalog.models import CatalogService
from apps.core.services.legal import LEGAL_PAGES, LegalIdentityService
from apps.core.services.marketing import PublicDtfOfferService
from apps.customers.models import DefaultCustomerVolumeDiscountTier
from django.template.loader import render_to_string
from django.test import Client, override_settings
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "backend" / "static_src"
PREMIUM_CSS = STATIC / "css" / "components" / "dtf-premium.css"
STICKY_JS = STATIC / "js" / "dtf-sticky-cta.js"
EMPTY_IDENTITY = {key: "" for key, _ in (
    *LegalIdentityService.PUBLISHER_FIELDS,
    *LegalIdentityService.CONTACT_FIELDS,
    *LegalIdentityService.HOST_FIELDS,
)}


def anonymous():
    return SimpleNamespace(user=SimpleNamespace(is_authenticated=False))


@pytest.mark.django_db
@pytest.mark.parametrize("page", LEGAL_PAGES, ids=lambda page: page.slug)
def test_legal_pages_are_public_and_cross_linked(page):
    response = Client().get(reverse(page.url_name))
    assert response.status_code == 200
    html = response.content.decode()
    assert f"<h1 id=\"legal-title\">{page.title}</h1>" in html
    for other in LEGAL_PAGES:
        assert f'href="{reverse(other.url_name)}"' in html
    assert html.count('aria-current="page"') == 1
    assert "exclusivement réservé aux professionnels (B2B)" in html


@pytest.mark.django_db
def test_legal_pages_stay_reachable_when_home_redirects_to_login(monkeypatch):
    monkeypatch.setenv("MARKETING_HOME_REDIRECT_TO_LOGIN", "1")
    assert Client().get(reverse("home")).status_code == 302
    assert Client().get(reverse("legal_notice")).status_code == 200


@pytest.mark.django_db
@override_settings(LEGAL_IDENTITY=EMPTY_IDENTITY, SUPPORT_CONTACT_EMAIL="")
def test_legal_notice_marks_missing_identity_instead_of_inventing_it():
    html = Client().get(reverse("legal_notice")).content.decode()
    assert html.count("À compléter") == len(EMPTY_IDENTITY)
    assert "Certaines informations sont en cours de renseignement." in html


@pytest.mark.django_db
def test_legal_notice_renders_configured_identity_and_support_fallback():
    identity = {**EMPTY_IDENTITY, "company_name": "Atelier Test SAS", "host_name": "Hôte Test"}
    with override_settings(LEGAL_IDENTITY=identity, SUPPORT_CONTACT_EMAIL="pro@example.test"):
        html = Client().get(reverse("legal_notice")).content.decode()
        home = Client().get(reverse("home")).content.decode()
    assert "Atelier Test SAS" in html and "Hôte Test" in html
    assert "pro@example.test" in html
    assert 'href="mailto:pro@example.test"' in home


@pytest.mark.django_db
def test_terms_page_repeats_only_published_commercial_conditions():
    html = Client().get(reverse("legal_terms")).content.decode()
    assert "6 € HT" in html
    assert "sans valeur de devis" in html
    assert "sans rétroactivité" in html
    for unsupported in ["24 h garanties", "correction gratuite", "100 % garanti"]:
        assert unsupported not in html


@pytest.mark.django_db
def test_home_footer_links_legal_pages_from_any_route():
    html = Client().get(reverse("home")).content.decode()
    footer = html.split('class="dtf-footer"', 1)[1]
    for page in LEGAL_PAGES:
        assert f'href="{reverse(page.url_name)}"' in footer
    assert f'href="{reverse("home")}#tarifs"' in footer
    assert "(nouvel onglet)" in footer


@pytest.mark.django_db
def test_access_actions_carry_verified_reassurance_for_visitors_only():
    html = Client().get(reverse("home")).content.decode()
    hero = html.split('class="dtf-hero dtf-shell"', 1)[1].split("</section>", 1)[0]
    final = html.split('id="acces"', 1)[1].split("</section>", 1)[0]
    for block in (hero, final):
        assert "Réponse sous 1 à 2 jours ouvrés" in block
        assert "Sans engagement" in block
    assert final.count("<li>") >= 3
    signed_in = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
    rendered = render_to_string("shop/partials/dtf/final.html", {"request": signed_in})
    assert "Sans engagement" not in rendered


@pytest.mark.django_db
def test_home_exposes_share_metadata_with_absolute_urls():
    html = Client().get(reverse("home")).content.decode()
    assert '<link rel="canonical" href="http://testserver/">' in html
    assert 'property="og:image" content="http://testserver/' in html
    assert "img/dtf/og-share.jpg" in html
    assert 'name="twitter:card" content="summary_large_image"' in html
    assert (STATIC / "img" / "dtf" / "og-share.jpg").stat().st_size < 150_000


def test_photo_placeholder_is_a_proof_sheet_without_actions():
    html = render_to_string("shop/partials/dtf/photo.html", {"photo_id": "p", "title": "Vue"})
    assert 'role="img"' in html
    assert "dtf-proof-marks" not in html
    assert 'class="dtf-proof-inks" aria-hidden="true"' in html
    assert "Photo à venir" in html
    assert "<button" not in html


@pytest.mark.django_db
def test_simulator_range_follows_the_published_tiers():
    CatalogService.objects.filter(service_type=CatalogService.ServiceType.DTF_TRANSFER).delete()
    CatalogService.objects.create(
        code="seed-dtf-meter", name="DTF au m²",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER, base_price="25.00",
    )
    DefaultCustomerVolumeDiscountTier.objects.all().delete()
    for minimum, percent in [(5, 10), (10, 20), (40, 25)]:
        DefaultCustomerVolumeDiscountTier.objects.create(
            minimum_monthly_linear_m=Decimal(minimum), discount_percent=Decimal(percent),
        )
    offer = PublicDtfOfferService().snapshot()
    assert offer["range_max_m"] == 80
    html = render_to_string(
        "shop/partials/dtf/pricing.html", {"request": anonymous(), "dtf_offer": offer},
    )
    assert 'id="monthly-volume-range" type="range" min="1" max="80"' in html
    assert 'id="monthly-volume" type="number" min="1" max="500"' in html
    assert "<span>80 m et +</span>" in html


@pytest.mark.django_db
def test_sticky_access_bar_is_visitor_only_and_hidden_without_script():
    html = Client().get(reverse("home")).content.decode()
    bar = html.split("data-sticky-cta", 1)[1].split("</div>", 1)[0]
    assert bar.startswith(" hidden>")
    assert "Demander mon accès pro" in bar
    assert "js/dtf-sticky-cta.js" in html
    script = STICKY_JS.read_text()
    assert "inert" in script and "IntersectionObserver" in script


def test_scroll_motion_is_progressive_and_respects_reduced_motion():
    css = PREMIUM_CSS.read_text()
    motion = css.split("@supports (animation-timeline: scroll())", 1)[1]
    assert motion.lstrip("{ \n").startswith("@media (prefers-reduced-motion: no-preference)")
    before = css.split("@supports (animation-timeline: scroll())", 1)[0]
    assert "animation-timeline" not in before
    assert "@media (prefers-reduced-motion: reduce)" in css


def _seed_public_tiers():
    CatalogService.objects.filter(service_type=CatalogService.ServiceType.DTF_TRANSFER).delete()
    CatalogService.objects.create(
        code="seed-dtf-meter", name="DTF au m²",
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
        unit=CatalogService.Unit.LINEAR_METER, base_price="25.00",
    )
    DefaultCustomerVolumeDiscountTier.objects.all().delete()
    for minimum, percent in [(5, 10), (10, 20)]:
        DefaultCustomerVolumeDiscountTier.objects.create(
            minimum_monthly_linear_m=Decimal(minimum), discount_percent=Decimal(percent),
        )


@pytest.mark.django_db
def test_hero_volume_chips_mirror_the_public_tiers_and_wait_for_script():
    _seed_public_tiers()
    html = Client().get(reverse("home")).content.decode()
    hero = html.split('class="dtf-hero dtf-shell"', 1)[1].split("</section>", 1)[0]
    tiers = hero.split("data-hero-tiers", 1)[1].split("</div>", 1)[0]
    assert tiers.startswith(" hidden>")
    assert 'aria-labelledby="hero-tiers-label"' in hero
    assert tiers.count("data-hero-tier=") == 3
    assert '>5 m</button>' in tiers and '>10 m</button>' in tiers
    assert "Dégressif selon votre volume mensuel." in hero  # Fallback text without script.
    landing = (STATIC / "js" / "dtf-landing.js").read_text()
    assert "renderHeroQuote(quote)" in landing
    assert "heroTiers.hidden = false" in landing


@pytest.mark.django_db
def test_hero_omits_volume_chips_without_tiers():
    CatalogService.objects.filter(service_type=CatalogService.ServiceType.DTF_TRANSFER).delete()
    html = Client().get(reverse("home")).content.decode()
    assert "data-hero-tiers" not in html


@pytest.mark.django_db
def test_found_pictures_are_local_light_and_credited_on_the_home_only():
    for name in ["rennes-vilaine-carte-postale.webp", "presse-a-chaud.webp"]:
        assert (STATIC / "img" / "dtf" / name).stat().st_size < 300_000
    home = Client().get(reverse("home")).content.decode()
    credits = home.split('class="dtf-footer__credits"', 1)[1].split("</p>", 1)[0]
    assert "commons.wikimedia.org/wiki/File:AB_9_-_RENNES_-_La_Vilaine.JPG" in credits
    assert "commons.wikimedia.org/wiki/File:HASHIMA_HP54_at_TechShop_Ark_Hills.jpg" in credits
    assert "domaine public" in credits and "CC0" in credits
    assert credits.count('rel="noopener noreferrer"') == 2
    legal = Client().get(reverse("legal_notice")).content.decode()
    assert "dtf-footer__credits" not in legal
    assert 'class="dtf-footer__wordmark" aria-hidden="true"' in legal


@pytest.mark.django_db
def test_preparation_steps_use_the_layer_drawings_instead_of_empty_frames():
    html = Client().get(reverse("home")).content.decode()
    carousel = html.split("data-preparation-carousel", 1)[1]
    carousel = carousel.split("data-preparation-controls", 1)[0]
    assert "dtf-photo__placeholder" not in carousel
    for drawing in ["expression.svg", "flower-white.svg", "flower-powder.svg"]:
        assert f"img/dtf/{drawing}" in carousel
    assert carousel.count('class="dtf-prep-drawing"') == 3
    assert carousel.count('alt="Dessin ') == 3


@pytest.mark.django_db
def test_ink_band_and_studio_capture_frame_the_page():
    html = Client().get(reverse("home")).content.decode()
    assert '<section class="dtf-section dtf-gamut-band" id="couleurs"' in html
    assert '<div class="dtf-shell dtf-gamut">' in html
    final = html.split('id="acces"', 1)[1].split("</section>", 1)[0]
    assert '<figure class="dtf-final__studio" data-ui>' in final
    assert "img/dtf/screens/gang-sheet-studio.webp" in final
    assert "Capture de démonstration du Studio Gang Sheet" in final


def test_surface_uses_two_typefaces_and_a_scroll_direction_access_bar():
    css = PREMIUM_CSS.read_text()
    assert "--ui-font-display: var(--ui-font-body);" in css
    assert "Space Grotesk" not in css
    assert "dtf-proof-marks" not in css
    script = STICKY_JS.read_text()
    assert "scrollingUp" in script and "passive: true" in script
