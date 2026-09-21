from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = Path(settings.BASE_DIR)
CSS_DIR = BASE_DIR / "static_src/css"
TEMPLATES_DIR = BASE_DIR / "templates"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class GangSheetLibraryUITests(SimpleTestCase):
    def test_library_list_is_an_operate_scan_surface(self) -> None:
        listing = source(TEMPLATES_DIR / "portal/client/gang_sheets/list.html")
        icons = source(TEMPLATES_DIR / "portal/client/gang_sheets/partials/icon.html")
        gang_css = source(CSS_DIR / "components/gang-sheet.css")
        polish = source(CSS_DIR / "components/product-polish.css")
        client_css = source(CSS_DIR / "entries/portal-client.css")
        portal_tags = source(BASE_DIR / "apps/portal/templatetags/portal_tags.py")

        self.assertIn('aria-label="Bibliothèque de planches DTF"', listing)
        self.assertNotIn("Bibliothèque</h2>", listing)
        self.assertNotIn("Aperçu disponible", listing)
        self.assertNotIn("Planche autonome", listing)
        self.assertNotIn("Estimation HT", listing)
        self.assertNotIn("empty_mark", listing)
        self.assertNotIn("gang-sheet-create-dialog__mark", listing)
        self.assertIn("Impression HT", listing)
        self.assertIn('placeholder="Nom ou n° de planche"', listing)
        self.assertIn("ui-list-tabs__count", listing)
        self.assertIn("count('all')", listing)
        self.assertNotIn("count('ordered')", listing)
        self.assertNotIn("Commandées", listing)
        self.assertNotIn("Voir la commande", listing)
        self.assertNotIn("gang-sheet-card__primary--view", listing)
        self.assertNotIn("sheet.order_id", listing)
        self.assertIn("client-gang-sheet-editor", listing)
        self.assertIn("gang-sheet-card__primary--order", listing)
        self.assertIn("is-ready", listing)
        self.assertIn("is-pending", listing)
        self.assertIn("Composition en cours", listing)
        self.assertIn("data-product-nav-details", listing)
        self.assertIn('name="more"', listing)
        self.assertIn('role="menu"', listing)
        self.assertIn("gang-sheet-card__stage", listing)
        self.assertNotIn("•••", listing)
        self.assertIn("Créer et ouvrir le studio", listing)
        self.assertIn("gang-sheet-create-dialog__copy", listing)

        self.assertIn('name == "chevron-right"', icons)
        self.assertIn('name == "more"', icons)

        self.assertIn("repeat(auto-fill, minmax(min(100%, 17.75rem), 1fr))", gang_css)
        self.assertIn("height: 16rem", gang_css)
        self.assertNotIn("background: #191919", gang_css)
        self.assertIn("object-fit: contain", gang_css)
        self.assertIn(".gang-sheet-card__stage", gang_css)
        self.assertIn("object-position: top center", gang_css)
        self.assertIn(".gang-sheet-card__menu-panel", gang_css)
        self.assertIn(".gang-sheet-card__primary-icon", gang_css)
        self.assertIn("top: 0.65rem", gang_css)
        self.assertIn("grid-template-columns: minmax(0, 1fr) minmax(12.5rem, 16.5rem)", gang_css)

        self.assertIn("body.product-shell .gang-sheet-card__preview", polish)
        self.assertIn("height: 16rem", polish)
        self.assertNotIn("radial-gradient(", polish)

        self.assertIn(".gang-sheet-page .gang-sheet-card__preview", client_css)
        self.assertIn("gang-sheet-card__primary--order", client_css)
        self.assertIn('PORTAL_CSS_ASSET_V = "20260921-inbox-badge-v1"', portal_tags)
