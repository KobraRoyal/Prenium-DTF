from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree

import pytest
from apps.catalog.models import CatalogService
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "backend" / "static_src"


@pytest.mark.django_db
def test_commercial_hero_explains_file_care_and_keeps_one_interactive_transfer():
    html = Client().get(reverse("home")).content.decode()
    hero = html.split('class="dtf-hero dtf-shell"', 1)[1].split("</section>", 1)[0]
    assert "Votre DTF." in hero and "Notre exigence." in hero
    assert "8 couleurs pour les professionnels" in hero
    assert "Vos fichiers contrôlés et préparés pour une impression nette" in hero
    assert "Commandez après validation de votre compte" in hero
    assert hero.count("data-transfer-stage") == 1
    assert hero.count('id="layer-tab-') == 4
    assert "img/dtf/transfer-sheet.svg" in hero
    assert "100 % garanti" not in hero
    assert "correction gratuite" not in hero


@pytest.mark.parametrize("authenticated", [False, True])
def test_simulator_has_a_direct_entrypoint_matching_the_visitors_access(authenticated):
    request = SimpleNamespace(user=SimpleNamespace(is_authenticated=authenticated))
    html = render_to_string("shop/partials/dtf/pricing.html", {
        "request": request,
        "dtf_offer": {"pricing": {"widthCm": 55}, "price_per_m": 13.75},
    })
    actions = html.split('class="dtf-pricing__actions"', 1)[1].split("</div>", 1)[0]
    target = reverse("portal:login" if authenticated else "prospects:step1")
    assert f'href="{target}"' in actions
    assert ('Accéder à mon espace' if authenticated else 'Demander mon accès pro') in actions
    assert 'href="#commander"' in actions
    assert "6 € HT" in html


class MarketingContent(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.summaries = []
        self._summary = None
        self._in_faq = False
        self._in_hero = False
        self.transfer_in_hero = []
        self.capture_sources = []
        self._capture = False
        self.photo_slots = []
        self.photo_placeholders = []
        self.photo_buttons = []
        self.headings = []
        self._heading = None
        self.images = []
        self.named_groups = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("role") == "group" and attrs.get("aria-label"):
            self.named_groups.append(attrs["aria-label"])
        if tag == "img":
            self.images.append(attrs)
        if "data-photo-slot" in attrs:
            self.photo_slots.append(attrs["data-photo-slot"])
        if "dtf-photo__placeholder" in attrs.get("class", "").split():
            self.photo_placeholders.append((tag, attrs))
        if "data-gallery" in attrs:
            self.photo_buttons.append((tag, attrs))
        if tag == "h2":
            self._heading = []
        if "id" in attrs:
            self.ids.append(attrs["id"])
        if tag == "section" and attrs.get("id") == "faq":
            self._in_faq = True
        if tag == "section" and "dtf-hero" in attrs.get("class", "").split():
            self._in_hero = True
        if "data-transfer-stage" in attrs:
            self.transfer_in_hero.append(self._in_hero)
        if tag == "summary":
            self._summary = []
        if tag == "button" and "data-product-screen" in attrs:
            self._capture = True
        if tag == "img" and self._capture:
            self.capture_sources.append((attrs.get("src"), attrs.get("alt", "")))

    def handle_data(self, data):
        if self._heading is not None:
            self._heading.append(data)
        if self._summary is not None:
            self._summary.append(data)

    def handle_endtag(self, tag):
        if tag == "h2" and self._heading is not None:
            self.headings.append(" ".join(" ".join(self._heading).split()))
            self._heading = None
        if tag == "summary" and self._summary is not None:
            if self._in_faq:
                self.summaries.append(" ".join(" ".join(self._summary).split()))
            self._summary = None
        if tag == "section":
            self._in_faq = False
            self._in_hero = False
        if tag == "button":
            self._capture = False


@pytest.mark.django_db
def test_home_has_actionable_faq_origin_and_real_product_captures():
    response = Client().get(reverse("home"))
    assert response.status_code == 200
    html = response.content.decode()
    parsed = MarketingContent()
    parsed.feed(html)
    assert len(parsed.ids) == len(set(parsed.ids))
    assert parsed.transfer_in_hero == [True]
    assert "Schéma de principe du gamut étendu, sans mesure comparative" in html
    assert "faq" in parsed.ids
    assert "atelier" in parsed.ids
    assert "imprimés près de Rennes" in html
    assert "livraison partout en France" in html
    assert "data-ribbon" not in html  # The scrolling ribbon above the h1 was removed.
    assert len([title for title in parsed.summaries if title.endswith("?")]) == 8
    for subject in [
        "fichiers",
        "Gang Sheet",
        "format de planche",
        "textile",
        "remises",
        "livrez",
        "pose",
    ]:
        assert any(subject in title for title in parsed.summaries)
    assert "6 € HT" in html
    assert "50 à 60 lavages" not in html
    assert "Origine France Garantie" not in html
    assert "La pose à la presse à chaud, sur le textile de votre choix." in html
    assert "Données et montants de démonstration" in html
    assert len(parsed.capture_sources) == 2
    for src, alt in parsed.capture_sources:
        assert "/img/dtf/screens/" in src
        assert "démonstration" in alt
        path = STATIC / "img" / "dtf" / "screens" / src.rsplit("/", 1)[-1]
        with Image.open(path) as shot:
            assert shot.width >= 1000
            assert shot.height >= 400
            assert "exif" not in shot.info
        assert path.stat().st_size < 250_000


def test_fine_detail_comparison_preserves_the_drawing_and_only_reinforces_one_stroke():
    original = ElementTree.fromstring(
        render_to_string("shop/partials/dtf/fine_detail_art.html")
    )
    prepared = ElementTree.fromstring(
        render_to_string("shop/partials/dtf/fine_detail_art.html", {"prepared": True})
    )
    original_paths = original.findall(".//path")
    prepared_paths = prepared.findall(".//path")
    assert len(original_paths) == len(prepared_paths)
    changes = []
    for before, after in zip(original_paths, prepared_paths, strict=True):
        assert before.get("d") == after.get("d")
        assert before.get("stroke") == after.get("stroke")
        if before.attrib != after.attrib:
            changes.append((before, after))
    assert len(changes) == 1
    before, after = changes[0]
    assert float(before.get("stroke-width")) < float(after.get("stroke-width"))


@pytest.mark.django_db
def test_home_groups_the_narrative_and_distributes_honest_photo_reservations():
    html = Client().get(reverse("home")).content.decode()
    parsed = MarketingContent()
    parsed.feed(html)
    assert parsed.photo_slots == [
        "result-finished", "result-type", "result-multicolor", "place-rennes", "context-press",
    ]
    assert len(parsed.photo_placeholders) == 3
    for tag, attrs in parsed.photo_placeholders:
        assert tag == "div"
        assert attrs.get("role") == "img"
        assert "Photographie IDS.Supply à venir" in attrs["aria-label"]
    # Only the two sourced pictures open the viewer; empty frames never do.
    assert [attrs["data-gallery"] for _tag, attrs in parsed.photo_buttons] == [
        "Rennes, la Vilaine", "La pose à la presse à chaud",
    ]
    assert len(parsed.headings) == 8
    assert len(set(parsed.headings)) == 8
    assert "data-prepress-demos" in html
    for target in ["details-fins", "couleur-textile", "transparences"]:
        assert target in parsed.ids
    assert "data-gallery-dialog" in html  # Kept ready for actual photo sources.


def test_photo_component_makes_only_a_supplied_source_actionable():
    rendered = render_to_string("shop/partials/dtf/photo.html", {
        "photo_id": "test-photo", "title": "Vue de test",
        "caption": "Légende de test", "image_src": "img/dtf/screens/order-by-file.webp",
        "alt_text": "Capture utilisée uniquement par le test du composant",
    })
    parsed = MarketingContent()
    parsed.feed(rendered)
    assert not parsed.photo_placeholders
    assert len(parsed.photo_buttons) == 1
    tag, attrs = parsed.photo_buttons[0]
    assert tag == "button"
    assert attrs["aria-label"] == "Agrandir : Vue de test"
    assert 'loading="lazy"' in rendered
    assert 'width="1200" height="800"' in rendered


@pytest.mark.django_db
def test_public_home_never_renders_source_less_viewer_images():
    parsed = MarketingContent()
    parsed.feed(Client().get(reverse("home")).content.decode())
    assert parsed.images  # The genuine portal captures are still present.
    assert all(image.get("src", "").strip() for image in parsed.images)
    assert not any("data-gallery-image" in image for image in parsed.images)


def test_transfer_fallback_is_a_self_contained_sheet_with_five_artworks():
    path = STATIC / "img" / "dtf" / "transfer-sheet.svg"
    content = path.read_text()
    svg = ElementTree.fromstring(content)
    assert svg.get("viewBox") == "0 0 400 320"
    assert path.stat().st_size < 100_000
    assert "localhost" not in content
    artworks = [node for node in svg.iter() if "data-artwork" in node.attrib]
    assert len(artworks) == 5
    assert {node.get("data-artwork") for node in artworks} == {"0", "1", "2", "3", "4"}
    film = next(node for node in svg.iter() if node.get("data-layer") == "0")
    assert any("dtf-pet-curl" in node.get("class", "").split() for node in film.iter())
    assert not any("dtf-transfer-mark" in node.get("class", "").split() for node in film.iter())
    for node in svg.iter():
        for value in node.attrib.values():
            if "url(" in value:
                assert value.startswith("url(#")
    fallback = render_to_string("shop/partials/dtf/anatomy.html")
    assert "img/dtf/transfer-sheet.svg" in fallback


@pytest.mark.django_db
def test_preparation_story_is_available_without_javascript_and_keeps_advanced_tools():
    html = Client().get(reverse("home")).content.decode()
    assert 'aria-roledescription="carrousel"' in html
    assert html.count('data-preparation-slide') == 3
    assert html.count('aria-roledescription="diapositive"') == 3
    for title in ["Contrôler", "Le blanc adapté", "Préparer"]:
        assert title in html
    assert html.index('data-preparation-carousel') < html.index('data-prepress-demos')
    assert html.index('data-prepress-demos') < html.index('data-analysis-canvas')
    assert 'data-preparation-controls hidden' in html
    assert 'Encres couleur et blanche certifiées OEKO‑TEX®.' in html
    assert 'laize maximale de 56 cm' in html
    assert 'largeur utile de 55 cm' in html  # Film width is distinct from usable Studio width.
    assert 'Pas de format de planche imposé' in html
    assert 'volume DTF réalisé chaque mois' in html
    assert 'ECO PASSPORT' not in html  # No certificate standard or number was supplied.


@pytest.mark.django_db
def test_sections_put_a_real_ordering_preview_before_unfinished_production_photos():
    html = Client().get(reverse("home")).content.decode()
    assert html.index('id="commander"') < html.index('id="tarifs"')
    assert html.index('id="tarifs"') < html.index('id="realisations"')
    ordering = html.split('id="commander"', 1)[1].split('</section>', 1)[0]
    assert "Déposez vos visuels séparément" in ordering
    assert "Le règlement comptant utilise le Studio Gang Sheet" in ordering
    assert 'href="#tarifs"' in ordering
    assert reverse("prospects:step1") not in ordering
    assert "Capture de démonstration" in ordering
    assert ordering.count('role="tabpanel"') == 2


@pytest.mark.django_db
def test_pricing_and_faq_preserve_material_commercial_conditions_in_the_new_copy():
    html = Client().get(reverse("home")).content.decode()
    faq = html.split('id="faq"', 1)[1].split('</section>', 1)[0]
    assert "En encours" in faq and "Au comptant" in faq
    assert "sans rétroactivité" in faq
    assert "marges et les pas de longueur" in faq
    assert "300 dpi" in faq and "essai sur votre support" in faq
    assert "Après validation de votre compte" in html
    for unsupported in ["24 h garanties", "correction gratuite", "100 % garanti"]:
        assert unsupported not in html


@pytest.mark.django_db
def test_landing_omits_redundant_notes_but_preserves_useful_disclosures():
    html = Client().get(reverse("home")).content.decode()
    for removed in [
        "Lecture du bas vers le haut avant pose", "épaisseurs exagérées",
        "Survolez le transfert pour séparer les couches", "dtf-transfer-summary",
        "Petits caractères et texture du textile, vus de près.",
        "Captures recadrées de l’interface réelle", "dtf-preparation__step",
    ]:
        assert removed not in html
    assert 'data-transfer-close' in html
    assert 'data-gamut-explanation' in html
    assert 'Capture de démonstration' in html
    assert 'Photo à venir' in html
    assert 'Simulations illustratives' in html
    assert '6 € HT' in html
    assert 'Comment s’appliquent les remises' in html
    assert 'Encres couleur et blanche certifiées OEKO‑TEX®.' in html
    assert html.count('<figcaption>') == 3  # Sourced pictures and the Studio capture only.


@pytest.mark.django_db
def test_gallery_exposes_progressive_navigation_without_fake_photo_actions():
    html = Client().get(reverse("home")).content.decode()
    parsed = MarketingContent()
    parsed.feed(html)
    assert 'data-photo-carousel' in html
    assert 'id="dtf-photo-track"' in html
    assert 'data-photo-controls hidden' in html
    assert 'aria-label="Photos précédentes"' in html
    assert 'aria-label="Photos suivantes"' in html
    assert html.count('aria-controls="dtf-photo-track"') == 2
    gallery = html.split('id="realisations"', 1)[1].split('</section>', 1)[0]
    assert "data-gallery=" not in gallery
    assert len([slot for slot in parsed.photo_slots if slot.startswith("result-")]) == 3


@pytest.mark.django_db
@pytest.mark.parametrize("with_pricing", [False, True])
def test_option_groups_have_supported_accessible_names(with_pricing):
    CatalogService.objects.filter(
        service_type=CatalogService.ServiceType.DTF_TRANSFER,
    ).delete()
    if with_pricing:
        CatalogService.objects.create(
            code="seed-dtf-meter", name="DTF au m²",
            service_type=CatalogService.ServiceType.DTF_TRANSFER,
            unit=CatalogService.Unit.LINEAR_METER, base_price="25.00",
        )
    parsed = MarketingContent()
    parsed.feed(Client().get(reverse("home")).content.decode())
    assert {"Les huit encres", "Étapes de préparation, défilement horizontal"}.issubset(
        parsed.named_groups
    )
    assert ("Grille de remise mensuelle" in parsed.named_groups) is with_pricing
