from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = Path(settings.BASE_DIR)
CSS_DIR = BASE_DIR / "static_src/css"
TEMPLATES_DIR = BASE_DIR / "templates"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class StudioPolishUITests(SimpleTestCase):
    def test_studio_polish_follows_the_editor_component(self) -> None:
        entry = source(CSS_DIR / "entries/studio.css")
        editor_import = '@import "../components/gang-sheet-studio.css";'
        polish_import = '@import "../components/studio-polish.css";'

        self.assertLess(entry.index(editor_import), entry.index(polish_import))
        self.assertLess(entry.index(polish_import), entry.index("@tailwind base"))

        polish = source(CSS_DIR / "components/studio-polish.css")
        self.assertNotIn("@layer", polish)
        self.assertIn("--gang-panel: var(--surface)", polish)
        self.assertIn("--gang-panel-subtle: var(--surface-raised)", polish)
        self.assertIn("--gang-ink: var(--ink)", polish)
        self.assertIn("--gang-accent: var(--brand)", polish)
        self.assertIn(".gang-editor__toolbar", polish)
        self.assertIn(".gang-editor__selection-tools", polish)
        self.assertIn(".gang-editor__mobile-tabs button.is-active", polish)
        self.assertIn(".gang-editor__mobile-tabs button > svg", polish)
        self.assertIn(".gang-inspector-panel--validation li.is-ok", polish)
        self.assertIn(".gang-crop-box", polish)
        self.assertIn(".gang-crop-controls", polish)
        self.assertIn(".gang-snap-guide", polish)
        self.assertIn(".gang-selection-marquee", polish)
        self.assertNotIn("#dcff1a", polish)
        self.assertNotIn("#1f66ff", polish)
        self.assertIn("@media (max-width: 47.99rem)", polish)
        self.assertNotIn("gradient(", polish)

    def test_studio_polish_is_unlayered_and_owns_interaction_accents(self) -> None:
        polish = source(CSS_DIR / "components/studio-polish.css")
        entry = source(CSS_DIR / "entries/studio.css")

        for selector in [
            ".gang-crop-box",
            ".gang-crop-mode button.is-active",
            ".gang-snap-guide",
            ".gang-selection-marquee",
            ".gang-sheet-item.is-selected",
            ".gang-sheet-item-action:focus-visible",
        ]:
            with self.subTest(selector=selector):
                self.assertIn(selector, polish)

        self.assertIn("background: var(--gang-accent)", polish)
        self.assertIn("outline-color: var(--gang-focus)", polish)
        self.assertNotIn("#dcff1a", polish)
        self.assertNotIn("#1f66ff", polish)

        for marker in [
            "body.product-shell--studio",
            "box-shadow: none !important",
            ".gang-editor__save",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, entry)

    def test_empty_gallery_has_one_import_path_and_keeps_htmx_contract(self) -> None:
        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")
        gallery = source(TEMPLATES_DIR / "portal/client/gang_sheets/partials/asset_gallery.html")

        self.assertIn("Ajouter des fichiers", editor)
        empty_state = gallery.split("{% empty %}", 1)[1]
        self.assertNotIn("<button", empty_state.split("{% endfor %}", 1)[0])
        self.assertNotIn("Ajouter un visuel", empty_state)
        for attribute in ["hx-get", "hx-trigger", "hx-target", "hx-swap", "hx-sync"]:
            self.assertIn(attribute, gallery)

    def test_final_step_describes_one_outcome_without_changing_actions(self) -> None:
        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")

        self.assertIn("Étape 4 — Finaliser la planche", editor)
        self.assertIn("Préparer le rendu", editor)
        self.assertIn("Préparer le rendu HD", editor)
        self.assertIn("Confirmer la composition", editor)
        self.assertIn("data-render-sheet", editor)
        self.assertIn("data-validate-sheet", editor)
        self.assertNotIn("Générer le rendu HD", editor)
