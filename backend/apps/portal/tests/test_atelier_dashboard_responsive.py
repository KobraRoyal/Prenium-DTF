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

    def test_chart_is_compact_and_tooltip_targets_the_highest_point(self) -> None:
        dashboard = (Path(settings.BASE_DIR) / "templates/portal/staff/dashboard.html").read_text(
            encoding="utf-8"
        )
        chart_script_path = Path(settings.BASE_DIR) / "static_src/js/atelier-dashboard-chart.js"
        chart_script = chart_script_path.read_text(encoding="utf-8")
        staff_css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("Tour de contrôle Atelier", dashboard)
        self.assertIn('label: "Nouvelles commandes"', chart_script)
        self.assertNotIn('label: "Entrées Atelier"', chart_script)
        self.assertIn("Tooltip.positioners.topmost", chart_script)
        self.assertIn('position: "topmost"', chart_script)
        self.assertIn("height:clamp(12rem,18vw,15rem)", staff_css)
