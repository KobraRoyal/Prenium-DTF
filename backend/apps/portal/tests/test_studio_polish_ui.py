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
        text_import = '@import "../components/gang-sheet-text.css";'
        polish_import = '@import "../components/studio-polish.css";'

        self.assertLess(entry.index(editor_import), entry.index(text_import))
        self.assertLess(entry.index(text_import), entry.index(polish_import))
        self.assertLess(entry.index(polish_import), entry.index("@tailwind base"))

        polish = source(CSS_DIR / "components/studio-polish.css")
        self.assertNotIn("@layer", polish)
        self.assertIn("--gang-panel: var(--surface)", polish)
        self.assertIn("--gang-panel-subtle: var(--surface-raised)", polish)
        self.assertIn("--gang-ink: var(--ink)", polish)
        self.assertIn("--gang-accent: var(--brand)", polish)
        self.assertIn(".gang-editor__toolbar", polish)
        self.assertIn(".gang-editor__toolbar-start", polish)
        self.assertIn(".gang-editor__toolbar-tools", polish)
        self.assertIn(".gang-editor__creation-tools", polish)
        self.assertIn(".gang-editor__save.is-saved", polish)
        self.assertIn(".gang-editor__save-icon--done", polish)
        self.assertIn(".gang-editor__inspector button", polish)
        self.assertIn(".gang-sheet-item-action", polish)
        self.assertIn("background: var(--gang-panel);", polish)
        self.assertIn(".gang-sheet-canvas-scroll", polish)
        self.assertIn("overflow: hidden", polish)
        self.assertIn("minmax(0, 14.5rem) minmax(0, 1fr) minmax(0, 16.25rem)", polish)
        self.assertIn("repeat(3, minmax(0, 1fr))", polish)
        self.assertIn("min(1540px, calc(100vw - 1.5rem))", polish)
        self.assertIn("height: max(30rem, calc(100dvh - 15.5rem))", polish)
        self.assertIn("16rem minmax(0, 1fr) 18rem", polish)
        self.assertIn('@media (min-width: 88rem)', polish)
        self.assertIn(".gang-editor__overview", polish)
        self.assertIn('grid-template-areas: "heading workflow metrics status"', polish)
        self.assertIn("display: contents", polish)
        self.assertIn("--gang-overview-gutter: 0.75rem", polish)
        self.assertIn("--gang-overview-section-gap: 0.5rem", polish)
        self.assertIn("minmax(18rem, 0.88fr)", polish)
        self.assertIn(".gang-workflow li + li", polish)
        self.assertIn('"sidebar toolbar inspector"', polish)
        self.assertIn("grid-column: 2", polish)
        self.assertIn(".gang-asset-card__usage-state", polish)
        self.assertIn("border-bottom-left-radius: 0", polish)
        self.assertIn(".gang-editor__selection-tools", polish)
        self.assertIn(".gang-inspector-panel--validation", polish)
        self.assertIn(".gang-sheet-order-quote__summary", polish)
        self.assertIn(".gang-sheet-order-quote__total", polish)
        self.assertIn("border-block: 1px solid", polish)
        self.assertIn(".gang-inspector-section__title", polish)
        self.assertIn(".gang-unit-field", polish)
        self.assertIn(".gang-asset-card__place", polish)
        self.assertIn(".gang-inspector-danger", polish)
        self.assertIn(".gang-inspector-panel--multi", polish)
        self.assertIn("position: sticky", polish)
        self.assertIn(".gang-editor__mobile-tabs button.is-active", polish)
        self.assertIn(".gang-editor__mobile-tabs button > svg", polish)
        self.assertIn(".gang-inspector-panel--validation li.is-ok", polish)
        self.assertIn(".gang-sheet-item__label", polish)
        self.assertIn(
            ".gang-sheet-item:is(:hover, :focus-within, .is-selected) .gang-sheet-item__label",
            polish,
        )
        self.assertIn(".gang-selection-frame__size", polish)
        self.assertIn(".gang-selection-frame__chrome", polish)
        self.assertIn("translate(-50%, calc(-100% - 0.4rem))", polish)
        self.assertIn("display: none", polish)
        self.assertIn(".gang-sheet-canvas:has(.gang-selection-frame.is-multiple)", polish)
        self.assertIn(".gang-crop-controls", polish)
        self.assertIn(".gang-snap-guide", polish)
        self.assertIn(".gang-selection-marquee", polish)
        self.assertIn(".is-marquee-selecting", polish)
        self.assertNotIn("#dcff1a", polish)
        self.assertNotIn("#1f66ff", polish)
        self.assertIn("@media (max-width: 47.99rem)", polish)
        self.assertNotIn("gradient(", polish)

        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")
        overview_start = editor.index('<div class="gang-editor__overview">')
        overview_end = editor.index('<dialog class="b2b-configurator-dialog', overview_start)
        overview = editor[overview_start:overview_end]
        self.assertIn('<header class="gang-editor__header">', overview)
        self.assertIn('<div class="gang-editor__progress-row">', overview)
        self.assertLess(
            overview.index('<header class="gang-editor__header">'),
            overview.index('<div class="gang-editor__progress-row">'),
        )

    def test_studio_polish_is_unlayered_and_owns_interaction_accents(self) -> None:
        polish = source(CSS_DIR / "components/studio-polish.css")
        entry = source(CSS_DIR / "entries/studio.css")
        core = source(CSS_DIR / "entries/portal-core.css")

        for selector in [
            ".gang-crop-box",
            ".gang-crop-mode button.is-active",
            ".gang-snap-guide",
            ".gang-selection-marquee",
            ".gang-sheet-item.is-selected",
            ".gang-selection-frame",
            ".gang-selection-frame.is-group",
            ".gang-group-tools",
            ".gang-sheet-item-action:focus-visible",
        ]:
            with self.subTest(selector=selector):
                self.assertIn(selector, polish)

        self.assertIn("background: var(--gang-accent)", polish)
        self.assertIn("outline-color: var(--gang-focus)", polish)
        self.assertNotIn("#dcff1a", polish)
        self.assertNotIn("#1f66ff", polish)

        self.assertIn(".gang-editor__workspace", entry)
        self.assertIn(".gang-editor__inspector button", entry)
        self.assertIn("> .gang-inspector-panel--validation", entry)
        self.assertIn("background: var(--surface) !important", entry)
        self.assertIn("grid-column: 3 !important", entry)
        self.assertIn('"toolbar toolbar toolbar"', entry)
        self.assertIn(".gang-editor__overview :is(", entry)
        self.assertIn("border-radius: 0 !important", entry)
        self.assertIn("border-left: 0 !important", entry)
        self.assertIn('"sidebar toolbar inspector"', entry)
        self.assertIn("grid-row: 1 / -1 !important", entry)
        self.assertIn(".is-mobile-active", entry)
        self.assertIn("flex-wrap: nowrap !important", entry)
        self.assertIn(":not(.gang-inspector-panel)", entry)
        core = source(CSS_DIR / "entries/portal-core.css")
        self.assertIn(":not(.gang-inspector-panel)", core)
        self.assertIn("box-shadow: none !important", entry)
        self.assertIn(".gang-editor__save", entry)
        self.assertIn(".gang-sheet-canvas-scroll", entry)
        self.assertIn("body.product-shell--studio", entry)

    def test_empty_gallery_has_one_import_path_and_keeps_htmx_contract(self) -> None:
        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")
        gallery = source(TEMPLATES_DIR / "portal/client/gang_sheets/partials/asset_gallery.html")

        self.assertIn("Ajouter des fichiers", editor)
        self.assertIn("gang-asset-card__place", gallery)
        self.assertIn("Placer sur la planche", gallery)
        empty_state = gallery.split("{% empty %}", 1)[1]
        self.assertNotIn("<button", empty_state.split("{% endfor %}", 1)[0])
        self.assertNotIn("Ajouter un visuel", empty_state)
        for attribute in ["hx-get", "hx-trigger", "hx-target", "hx-swap", "hx-sync"]:
            self.assertIn(attribute, gallery)
        self.assertIn('class="gang-asset-card__usage-state"', gallery)
        self.assertNotIn('class="gang-asset-card__remove"\n            disabled', gallery)

    def test_final_step_uses_one_confirm_cta(self) -> None:
        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")
        editor_js = source(BASE_DIR / "static_src/js/gang-sheet-editor.js")
        app_js = source(BASE_DIR / "static_src/js/app.js")

        self.assertIn("Étape 4 — Finaliser la planche", editor)
        self.assertIn("Confirmer la composition", editor)
        self.assertIn("data-validate-sheet", editor)
        self.assertIn("data-validate-label", editor)
        self.assertNotIn("Préparer le rendu HD", editor)
        self.assertNotIn("data-render-sheet", editor)
        self.assertNotIn("Générer le rendu HD", editor)
        self.assertIn("data-snap-toggle", editor)
        self.assertIn("data-zoom-in", editor)
        self.assertIn("data-zoom-fit", editor)
        self.assertIn("data-save-label", editor)
        self.assertIn("gang-editor__save-icon", editor)
        self.assertIn("gang-tool-btn--icon gang-editor__save", editor)
        self.assertIn("gang-editor__save-group", editor)
        self.assertIn("gang-editor__toolbar-start", editor)
        self.assertIn("gang-editor__creation-tools", editor)
        self.assertNotIn("gang-editor__toolbar-group--create", editor)
        self.assertNotIn("gang-editor__toolbar-group--impose", editor)
        self.assertEqual(editor.count('class="gang-editor__toolbar"'), 1)
        self.assertLess(
            editor.index('class="gang-editor__toolbar"'),
            editor.index('class="gang-editor__stage'),
        )
        self.assertIn("data-validation-panel", editor)
        self.assertIn("data-multi-inspector", editor)
        self.assertIn("data-rotate-selection", editor)
        self.assertIn("gang-inspector-section__title", editor)
        self.assertIn("gang-unit-field", editor)
        self.assertIn("Aligner et répartir", editor)
        self.assertIn("data-create-order-project", editor)
        self.assertIn(
            "ui-btn {% if can_create_order and can_edit %}ui-btn-primary{% else %}"
            "ui-btn-secondary is-disabled{% endif %}",
            editor,
        )
        self.assertNotIn("data-metric-price", editor)
        self.assertEqual(editor.count("Total estimé HT"), 1)
        self.assertIn('data-sheet-order-quote role="status" aria-live="polite"', editor)
        self.assertLess(editor.index("data-sheet-order-quote"), editor.index("data-validate-sheet"))
        self.assertIn('validateBtn.hidden = state.status === "validated"', editor_js)
        self.assertIn('link.hidden = !canCreate', editor_js)
        self.assertIn('link.classList.toggle("ui-btn-primary", canCreate)', editor_js)
        self.assertIn('const hasEstimate = state.items.length > 0 && quote.surface > 0', editor_js)
        self.assertNotIn('q("[data-metric-price]")', editor_js)
        self.assertIn('gang-sheet-editor.js?v=20260828-studio-groups-v23', app_js)
        self.assertNotIn("gang-inspector-panel__context", editor)
        text_css = source(CSS_DIR / "components/gang-sheet-text.css")
        self.assertIn("font-size: 2.18cqw", text_css)
        self.assertIn("word-break: normal", text_css)
        self.assertIn("container-type: inline-size", text_css)
        self.assertIn(".gang-sheet-item__text-rotator", text_css)
        self.assertIn(".gang-sheet-item__text-editor", text_css)
        self.assertIn(".gang-sheet-text-hint", text_css)
        self.assertIn("overflow: auto", text_css)
        self.assertIn(
            ".gang-sheet-item.is-text .gang-sheet-item__preview {\n  background: transparent;",
            text_css,
        )
        self.assertIn("Gang Inter", text_css)
        self.assertNotIn("62cqmin", text_css)

    def test_studio_preview_src_does_not_assign_dom_json_url_to_image(self) -> None:
        editor_js = source(BASE_DIR / "static_src/js/gang-sheet-editor.js")
        after_helper = editor_js.split("function trustedAssetPreviewSrc", 1)[1]

        self.assertIn("function trustedAssetPreviewSrc(versionPublicId)", editor_js)
        self.assertIn("encodeURIComponent(versionPublicId)", editor_js)
        self.assertIn("image.src = previewSrc", editor_js)
        self.assertNotIn("item.preview_url", after_helper)
