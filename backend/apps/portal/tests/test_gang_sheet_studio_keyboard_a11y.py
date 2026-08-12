from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
STATIC_SRC_DIR = Path(settings.BASE_DIR) / "static_src"


class GangSheetStudioKeyboardAccessibilityTests(SimpleTestCase):
    def test_mobile_sections_follow_the_aria_tabs_contract(self) -> None:
        editor = (
            TEMPLATES_DIR / "portal/client/gang_sheets/editor.html"
        ).read_text(encoding="utf-8")
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(
            encoding="utf-8"
        )

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
        editor = (
            TEMPLATES_DIR / "portal/client/gang_sheets/editor.html"
        ).read_text(encoding="utf-8")
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('role="application"', editor)
        self.assertIn('data-sheet-canvas role="region" tabindex="0"', editor)
        self.assertIn('aria-describedby="gang-sheet-keyboard-help"', editor)
        self.assertIn("aria-keyshortcuts", editor)
        self.assertIn("function shouldIgnoreStudioShortcut", runtime)
        self.assertIn("!root.contains(target)", runtime)
        self.assertIn("canvas.contains(target)", runtime)
        self.assertIn("input, textarea, select, [contenteditable]", runtime)
        self.assertIn("return true;", runtime)

    def test_resize_rendering_is_throttled_by_animation_frame(self) -> None:
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(
            encoding="utf-8"
        )

        self.assertIn("let resizeFrame = null", runtime)
        self.assertIn("if (resizeFrame !== null) return", runtime)
        self.assertIn("resizeFrame = window.requestAnimationFrame", runtime)

    def test_workflow_reflects_real_studio_state_and_navigates_panels(self) -> None:
        editor = (
            TEMPLATES_DIR / "portal/client/gang_sheets/editor.html"
        ).read_text(encoding="utf-8")
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(
            encoding="utf-8"
        )

        for step in ["import", "compose", "control", "validate"]:
            self.assertIn(f'data-workflow-step="{step}"', editor)
        self.assertIn("const assetCount", runtime)
        self.assertIn("const itemCount = state.items.length", runtime)
        self.assertIn("const issueCount = state.issues.length", runtime)
        self.assertIn('status === "validated"', runtime)
        self.assertIn("const currentStep", runtime)
        self.assertIn('node.setAttribute("aria-current", "step")', runtime)
        self.assertIn("[data-workflow-panel-target]", runtime)
        self.assertIn("setMobilePanel(panelName", runtime)

    def test_advanced_composition_tools_use_native_disclosure(self) -> None:
        editor = (
            TEMPLATES_DIR / "portal/client/gang_sheets/editor.html"
        ).read_text(encoding="utf-8")
        runtime = (STATIC_SRC_DIR / "js/gang-sheet-editor.js").read_text(
            encoding="utf-8"
        )

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
