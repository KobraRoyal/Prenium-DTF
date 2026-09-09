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
        dashboard_panel = (
            Path(settings.BASE_DIR)
            / "templates/portal/staff/partials/dashboard_worklist_panel.html"
        ).read_text(encoding="utf-8")
        staff_css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("Tour de contrôle Atelier", dashboard)
        self.assertIn('label: "Nouvelles commandes"', chart_script)
        self.assertNotIn('label: "Entrées Atelier"', chart_script)
        self.assertIn('class="atelier-production-chart atelier-production-rail"', dashboard_panel)
        self.assertIn("atelier-production-activity", dashboard_panel)
        self.assertIn("activity_kpi_rows", dashboard_panel)
        self.assertIn('class="atelier-dashboard-secondary-rail', dashboard_panel)
        self.assertIn("atelier-production-gauge__canvas", dashboard_panel)
        self.assertIn('type: "doughnut"', chart_script)
        self.assertIn("circumference: 180", chart_script)
        self.assertIn("Tooltip.positioners.topmost", chart_script)
        self.assertIn('position: "topmost"', chart_script)
        self.assertIn("height:clamp(12rem,18vw,15rem)", staff_css)
        self.assertIn("atelier-dashboard-secondary-rail--with-financials", staff_css)
        self.assertIn("atelier-production-activity { display:grid", staff_css)
        self.assertIn("grid-template-columns:repeat(4,minmax(0,1fr))", staff_css)

    def test_production_health_is_compact_accessible_and_responsive(self) -> None:
        dashboard_panel = (
            Path(settings.BASE_DIR)
            / "templates/portal/staff/partials/dashboard_worklist_panel.html"
        ).read_text(encoding="utf-8")
        staff_css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )

        self.assertIn('id="atelier-production-health"', dashboard_panel)
        self.assertIn('aria-labelledby="atelier-production-health-title"', dashboard_panel)
        self.assertIn('aria-labelledby="atelier-production-alerts-title"', dashboard_panel)
        self.assertIn('aria-labelledby="atelier-production-efficiency-title"', dashboard_panel)
        self.assertIn("production_health.alerts", dashboard_panel)
        self.assertIn("production_health.quality", dashboard_panel)
        self.assertIn("production_health.flow", dashboard_panel)
        self.assertIn("{% if alert.href %}", dashboard_panel)
        self.assertIn("Commandes bloquées", dashboard_panel)
        self.assertIn("Taux de réimpression", dashboard_panel)
        self.assertIn("Délai moyen", dashboard_panel)
        self.assertIn(
            ".atelier-production-health__body { display:grid; "
            "grid-template-columns:1fr; gap:.75rem; }",
            staff_css,
        )
        self.assertIn('grid-template-areas:"label value" "detail detail"', staff_css)
        self.assertIn(".atelier-production-efficiency { grid-template-columns:1fr; }", staff_css)
        self.assertIn(".atelier-production-alert > a:focus-visible", staff_css)
        self.assertIn(".atelier-production-health__body { grid-template-columns:1fr", staff_css)
