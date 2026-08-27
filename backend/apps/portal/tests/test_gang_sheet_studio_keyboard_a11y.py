from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
STATIC_SRC_DIR = Path(settings.BASE_DIR) / "static_src"


class GangSheetStudioKeyboardAccessibilityTests(SimpleTestCase):
    def test_mobile_sections_follow_the_aria_tabs_contract(self) -> None:
        editor = (TEMPLATES_DIR / "portal/client/gang_sheets/editor.html").read_text(
            encoding="utf-8"
        )
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")

        self.assertIn('role="tablist"', editor)
        self.assertEqual(editor.count('role="tab"'), 3)
        self.assertEqual(editor.count('role="tabpanel"'), 3)
        self.assertIn('aria-labelledby="gang-editor-tab-canvas"', editor)
        self.assertIn("handleMobileTabKeydown", runtime)
        for key in ["ArrowRight", "ArrowLeft", "Home", "End"]:
            self.assertIn(f'event.key === "{key}"', runtime)
        self.assertIn("tab.tabIndex = active ? 0 : -1", runtime)
        self.assertIn("panel.hidden = isMobile && !active", runtime)
        self.assertIn('panel.setAttribute("role", "tabpanel")', runtime)
        self.assertIn('panel.removeAttribute("role")', runtime)

    def test_canvas_shortcuts_are_scoped_and_discoverable(self) -> None:
        editor = (TEMPLATES_DIR / "portal/client/gang_sheets/editor.html").read_text(
            encoding="utf-8"
        )
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")

        self.assertNotIn('role="application"', editor)
        self.assertIn('data-sheet-canvas role="region" tabindex="0"', editor)
        self.assertIn('aria-describedby="gang-sheet-keyboard-help"', editor)
        self.assertIn("aria-keyshortcuts", editor)
        self.assertIn("function shouldIgnoreStudioShortcut", runtime)
        self.assertIn("!root.contains(target)", runtime)
        self.assertIn("canvas.contains(target)", runtime)
        self.assertIn("input, textarea, select, [contenteditable]", runtime)
        self.assertIn("return true;", runtime)

    def test_canvas_zoom_fits_selection_without_changing_layout(self) -> None:
        editor = (TEMPLATES_DIR / "portal/client/gang_sheets/editor.html").read_text(
            encoding="utf-8"
        )
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")
        icons = (
            TEMPLATES_DIR / "portal/client/gang_sheets/partials/icon.html"
        ).read_text(encoding="utf-8")

        self.assertIn("data-zoom-fit", editor)
        self.assertIn("data-zoom-in", editor)
        self.assertIn("data-zoom-out", editor)
        self.assertIn("data-zoom-reset", editor)
        self.assertIn('aria-keyshortcuts="Shift+2"', editor)
        self.assertIn("Maj plus 2 cadre l’objet ou le groupe sélectionné", editor)
        self.assertIn("Plus et moins zooment en conservant le visuel visé", editor)
        self.assertIn('name == "zoom-fit"', icons)
        self.assertIn("const ZOOM_MIN = 0.5", runtime)
        self.assertIn("const ZOOM_MAX = 4", runtime)
        self.assertIn("function zoomToFitTarget", runtime)
        self.assertIn("function setZoom", runtime)
        self.assertIn("function zoomAnchorMm", runtime)
        self.assertIn("function scrollViewportToMm", runtime)
        self.assertIn("function shouldIgnoreZoomShortcut", runtime)
        self.assertIn('event.code === "Digit2"', runtime)
        self.assertIn("zoomWheelAcc", runtime)
        self.assertIn("{ passive: false }", runtime)
        self.assertIn("Cadrer le groupe sélectionné", runtime)
        self.assertIn("Cadrer la sélection", runtime)
        self.assertNotIn("Math.min(1.5, round(zoom + 0.25, 2))", runtime)
        self.assertNotIn("item.x_mm", runtime.split("function zoomToFitTarget")[1].split("function ")[0])

    def test_resize_rendering_is_throttled_by_animation_frame(self) -> None:
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")

        self.assertIn("let resizeFrame = null", runtime)
        self.assertIn("if (resizeFrame !== null) return", runtime)
        self.assertIn("resizeFrame = window.requestAnimationFrame", runtime)

    def test_workflow_reflects_real_studio_state_and_navigates_panels(self) -> None:
        editor = (TEMPLATES_DIR / "portal/client/gang_sheets/editor.html").read_text(
            encoding="utf-8"
        )
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")

        for step in ["import", "compose", "control", "validate"]:
            self.assertIn(f'data-workflow-step="{step}"', editor)
        for accessible_name in [
            "Étape 1 — Importer les fichiers",
            "Étape 2 — Composer la planche",
            "Étape 3 — Contrôler la composition",
            "Étape 4 — Finaliser la planche",
        ]:
            self.assertIn(f'aria-label="{accessible_name}"', editor)
        self.assertIn("const assetCount", runtime)
        self.assertIn("const itemCount = state.items.length", runtime)
        self.assertIn("const issueCount = state.issues.length", runtime)
        self.assertIn('status === "validated"', runtime)
        self.assertIn("const currentStep", runtime)
        self.assertIn('node.setAttribute("aria-current", "step")', runtime)
        self.assertIn("[data-workflow-panel-target]", runtime)
        self.assertIn("setMobilePanel(panelName", runtime)

    def test_advanced_composition_tools_use_native_disclosure(self) -> None:
        editor = (TEMPLATES_DIR / "portal/client/gang_sheets/editor.html").read_text(
            encoding="utf-8"
        )
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")

        self.assertIn("data-advanced-selection-tools", editor)
        self.assertIn("data-advanced-spacing-tools", editor)
        self.assertGreaterEqual(editor.count("<details"), 2)
        for marker in [
            "data-align=",
            "data-distribute=",
            "data-selection-gap",
            "data-spacing-x",
            "data-spacing-y",
            "data-apply-spacing",
        ]:
            self.assertIn(marker, editor)
        self.assertIn("selectionCount > 1", runtime)
        self.assertIn("advancedSelectionTools.open = true", runtime)

    def test_canvas_text_tool_is_discoverable_and_inspectable(self) -> None:
        editor = (TEMPLATES_DIR / "portal/client/gang_sheets/editor.html").read_text(
            encoding="utf-8"
        )
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(encoding="utf-8")
        icons = (
            TEMPLATES_DIR / "portal/client/gang_sheets/partials/icon.html"
        ).read_text(encoding="utf-8")

        self.assertIn("data-add-text", editor)
        self.assertIn('aria-label="Ajouter un texte"', editor)
        self.assertIn("data-text-inspector", editor)
        self.assertIn("data-text-content", editor)
        self.assertIn("data-text-font", editor)
        self.assertIn("data-text-size", editor)
        self.assertIn("data-text-color", editor)
        self.assertIn("data-text-align", editor)
        self.assertIn("data-text-bold", editor)
        self.assertIn('name == "text"', icons)
        self.assertIn("function isTextItem", runtime)
        self.assertIn('body.append("kind", "text")', runtime)
        self.assertIn("function fittedTextBoxMm", runtime)
        self.assertIn("function textMaxWidthMm", runtime)
        self.assertIn("nextCenterX = itemCenterX", runtime)
        self.assertIn("quarter ? state.height_mm : state.width_mm", runtime)
        self.assertIn("function clampItemOnSheet", runtime)
        self.assertIn("gang-sheet-item__text-rotator", runtime)
        self.assertIn("function startCanvasTextEdit", runtime)
        self.assertIn("function insertCanvasTextNewline", runtime)
        self.assertIn("function isPlaceholderText", runtime)
        self.assertIn("data-canvas-text-hint", editor)
        self.assertIn("function syncSaveControl", runtime)
        self.assertIn('saveButton.setAttribute("aria-label", saveText)', runtime)
        self.assertIn("Échap termine", editor)
        self.assertIn("Entrée : nouvelle ligne", editor)
        self.assertIn('textItem ? "div" : "button"', runtime)
        self.assertIn("data-canvas-text-editor", runtime)
        self.assertIn("gang-sheet-item__text-editor", runtime)
        self.assertIn("function applyFittedTextBox", runtime)
        self.assertIn("function scaleTextFromCorner", runtime)
        self.assertIn("TEXT_MEASURE_PX_PER_MM", runtime)
        self.assertIn("RESIZE_CORNERS", runtime)
        self.assertIn("gang-sheet-item__resize--", runtime)
        self.assertIn("state.width_mm) || 1)) * 100}cqw", runtime)
        self.assertIn('event.key === "Enter"', runtime)
        self.assertIn("document.activeElement !== content", runtime)
        self.assertIn("Entrée passe à la ligne", editor)
        self.assertIn("Cliquez le texte pour l’écrire", editor)
        self.assertIn("La zone suit le texte", editor)
        text_css = (STATIC_SRC_DIR / "css/components/gang-sheet-text.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("function textSizeMm", runtime)
        self.assertIn("Helvetica", editor)
        self.assertIn("Montserrat", editor)
        self.assertIn("font-size: 2.18cqw", text_css)
        self.assertIn("word-break: normal", text_css)
        self.assertIn(".gang-sheet-item__text", text_css)
        self.assertIn(".gang-sheet-item__text-rotator", text_css)
        self.assertIn(".gang-sheet-item__text-editor", text_css)
        self.assertIn("overflow: auto", text_css)
        self.assertIn(".gang-sheet-text-hint", text_css)
        self.assertIn("outline: 1px solid var(--brand, #ff8775)", text_css)
        self.assertIn(
            ".gang-sheet-item.is-text .gang-sheet-item__preview {\n  background: transparent;",
            text_css,
        )
        self.assertIn("container-type: inline-size", text_css)
        self.assertNotIn(
            ".gang-sheet-item.is-text .gang-sheet-item__preview {\n  container-type: size;",
            text_css,
        )
        self.assertIn("Gang Inter", text_css)
        self.assertIn("function fontCssFamily", runtime)
        self.assertIn('error.code === "STALE_REVISION"', runtime)
        self.assertIn('node.classList.add("is-text")', runtime)
        self.assertIn("input, textarea, select, [contenteditable]", runtime)
