from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC_SRC_DIR = Path(settings.BASE_DIR) / "static_src"


class GangSheetMobileMetricsTests(SimpleTestCase):
    def css_source(self, name: str) -> str:
        return (STATIC_SRC_DIR / f"css/components/{name}").read_text(encoding="utf-8")

    def test_mobile_metrics_reflow_without_horizontal_scrolling(self) -> None:
        studio_css = (STATIC_SRC_DIR / "css/components/gang-sheet-studio.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", studio_css)
        self.assertIn("grid-column: 1 / -1", studio_css)
        self.assertIn("overflow: visible", studio_css)
        self.assertNotIn(".gang-editor__metrics {\n      display: flex", studio_css)

    def test_canvas_has_a_high_contrast_work_area_boundary(self) -> None:
        studio_css = (STATIC_SRC_DIR / "css/components/gang-sheet-studio.css").read_text(
            encoding="utf-8"
        )

        self.assertIn("border: 2px solid var(--product-line, #0b0b0b)", studio_css)
        self.assertIn("repeating-conic-gradient(#d9d5cc", studio_css)
        self.assertIn("0 0 0 3px var(--product-panel, #fffdf8)", studio_css)

    def test_mobile_editor_panels_keep_hidden_semantics(self) -> None:
        studio_css = self.css_source("gang-sheet-studio.css")
        polish_css = self.css_source("studio-polish.css")
        hidden_rule = ".gang-editor__workspace > [data-editor-panel][hidden]"

        self.assertIn(hidden_rule, studio_css)
        self.assertIn(f"body.product-shell--studio {hidden_rule}", polish_css)
        self.assertGreaterEqual(
            studio_css.count("display: none !important;"),
            1,
        )
        self.assertIn(
            f"body.product-shell--studio {hidden_rule} {{\n  display: none !important;\n}}",
            polish_css,
        )

    def test_small_desktop_finalization_does_not_cover_inspector_fields(self) -> None:
        studio_css = self.css_source("gang-sheet-studio.css")
        polish_css = self.css_source("studio-polish.css")
        finalization_rule = (
            "body.product-shell--studio .gang-inspector-panel--validation {\n  position: static;"
        )

        self.assertIn(finalization_rule, polish_css)
        self.assertIn("height: max(26rem, calc(100dvh - 15.5rem));", polish_css)
        self.assertIn(".gang-editor__inspector {\n", studio_css)
        self.assertIn("overflow-y: auto;", studio_css)
        self.assertIn("[data-preflight-panel]", polish_css)

    def test_mobile_workflow_labels_use_the_action_text_floor(self) -> None:
        studio_css = self.css_source("gang-sheet-studio.css")
        mobile_label_rule = studio_css.split(
            ".gang-workflow--editor li > button > span:last-child strong {",
            1,
        )[1].split("}", 1)[0]

        self.assertIn("font-size: var(--gang-text-action);", mobile_label_rule)
        self.assertIn("line-height: 1.25;", mobile_label_rule)
        self.assertIn("white-space: nowrap;", mobile_label_rule)
