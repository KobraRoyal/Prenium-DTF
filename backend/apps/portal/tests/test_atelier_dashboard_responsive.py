from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class AtelierDashboardResponsiveTests(SimpleTestCase):
    def test_shell_children_can_shrink_without_disabling_local_tab_scroll(self) -> None:
        product_css = (
            Path(settings.BASE_DIR) / "static_src/css/components/product-shell.css"
        ).read_text(encoding="utf-8")

        shrink_contract = """body.product-shell .atelier-dashboard-head,
body.product-shell .atelier-dashboard-metrics,
body.product-shell .atelier-worklist {
  min-width: 0;
  max-width: 100%;
}"""

        self.assertIn(shrink_contract, product_css)
        self.assertIn("body.product-shell .atelier-worklist__tabs", product_css)
        self.assertIn("overflow-x: auto", product_css)
