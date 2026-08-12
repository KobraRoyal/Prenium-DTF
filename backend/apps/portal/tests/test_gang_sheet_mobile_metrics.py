from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

STATIC_SRC_DIR = Path(settings.BASE_DIR) / "static_src"


class GangSheetMobileMetricsTests(SimpleTestCase):
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
