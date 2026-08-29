"""Contrat UI homogène — vues portail client et Atelier (page par page)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"

CLIENT_PAGE_VIEWS = [
    "portal/client/dashboard.html",
    "portal/client/checkout.html",
    "portal/client/orders_list.html",
    "portal/client/order_detail.html",
    "portal/client/order_projects_list.html",
    "portal/client/order_project_detail.html",
    "portal/client/order_project_form.html",
    "portal/client/gang_sheets/create_order_project.html",
    "portal/client/gang_sheets/list.html",
    "portal/client/team.html",
    "portal/profile.html",
]

STAFF_PAGE_VIEWS = [
    "portal/staff/dashboard.html",
    "portal/staff/operations/index.html",
    "portal/staff/orders_list.html",
    "portal/staff/order_detail.html",
    "portal/staff/order_projects_list.html",
    "portal/staff/customers/list.html",
    "portal/staff/customers/detail.html",
    "portal/staff/access_requests/list.html",
    "portal/staff/machines/index.html",
    "portal/staff/email_templates/list.html",
    "portal/staff/email_templates/edit.html",
    "portal/staff/settings/branding.html",
    "portal/staff/gang_sheets/settings.html",
    "portal/staff/customers/default_volume_discounts.html",
]

STAFF_FOCUS_VIEWS = [
    "portal/staff/order_project_detail.html",
    "portal/staff/access_requests/detail.html",
]

STAFF_PANEL_VIEWS = [
    "portal/staff/panels/billing.html",
    "portal/staff/panels/uploads.html",
    "portal/staff/panels/production.html",
    "portal/staff/panels/shipping.html",
    "portal/staff/panels/inspection.html",
    "portal/staff/panels/drive_sync.html",
]

STAFF_ATELIER_VIEWS = STAFF_PAGE_VIEWS + STAFF_FOCUS_VIEWS + STAFF_PANEL_VIEWS

CLIENT_ORDER_PANELS = [
    "portal/client/panels/billing.html",
    "portal/client/panels/uploads.html",
    "portal/client/panels/production.html",
    "portal/client/panels/shipping.html",
    "portal/client/panels/inspection.html",
]

ALL_PORTAL_PAGE_VIEWS = CLIENT_PAGE_VIEWS + STAFF_PAGE_VIEWS + STAFF_FOCUS_VIEWS

LEGACY_PATTERNS = [
    (r'class="btn"', 'class="btn"'),
    ("product-eyebrow", "product-eyebrow"),
    ("agency-", "agency-"),
    (r"\bopacity-\d+\b", "opacity-* utility"),
]

RAW_EMPTY_STATE = re.compile(
    r'<div[^>]*class="[^"]*\bempty-state\b[^"]*"[^>]*>',
    re.IGNORECASE,
)

EMPTY_STATE_EXCEPTIONS = {
    "portal/client/gang_sheets/list.html": "Alpine filtered empty (x-show)",
}


def template_source(relative_path: str) -> str:
    return (TEMPLATES_DIR / relative_path).read_text(encoding="utf-8")


def staff_dashboard_source() -> str:
    return template_source("portal/staff/dashboard.html") + template_source(
        "portal/staff/partials/dashboard_worklist_panel.html"
    )


class PortalViewsUiHomogeneityTests(SimpleTestCase):
    def test_client_pages_use_portal_page_client_shell(self) -> None:
        for path in CLIENT_PAGE_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('extends "portal/layout.html"', source)
                self.assertIn("portal-page--client", source)
                self.assertIn("page_head.html", source)

    def test_staff_list_pages_use_portal_page_staff_shell(self) -> None:
        for path in STAFF_PAGE_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('extends "portal/layout.html"', source)
                self.assertIn("portal-page--staff", source)
                self.assertIn("page_head.html", source)

    def test_staff_focus_pages_use_portal_page_staff_without_page_head(self) -> None:
        focus_markers = (
            "staff-project-focus",
            "staff-access-focus",
        )
        for path in STAFF_FOCUS_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn("portal-page--staff", source)
                self.assertNotIn("page_head.html", source)
                self.assertTrue(any(marker in source for marker in focus_markers))

    def test_all_portal_pages_expose_portal_page_surface(self) -> None:
        for path in ALL_PORTAL_PAGE_VIEWS:
            with self.subTest(path=path):
                self.assertIn("portal-page-surface", template_source(path))

    def test_portal_page_titles_use_em_dash_brand_suffix(self) -> None:
        for path in ALL_PORTAL_PAGE_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                match = re.search(r"{% block title %}(.*?){% endblock %}", source, re.DOTALL)
                self.assertIsNotNone(match, f"{path} : block title manquant")
                title = match.group(1).strip()
                self.assertIn("— Prenium DTF", title, f"{path} : titre sans suffixe marque")

    def test_portal_pages_avoid_legacy_visual_patterns(self) -> None:
        for path in ALL_PORTAL_PAGE_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                for pattern, label in LEGACY_PATTERNS:
                    self.assertIsNone(re.search(pattern, source), f"{path} : reliquat {label}")

    def test_portal_pages_prefer_shared_empty_state_partial(self) -> None:
        for path in ALL_PORTAL_PAGE_VIEWS:
            if path in EMPTY_STATE_EXCEPTIONS:
                continue
            with self.subTest(path=path):
                source = template_source(path)
                for match in RAW_EMPTY_STATE.finditer(source):
                    snippet = source[max(0, match.start() - 40) : match.end() + 80]
                    if "empty_state.html" in snippet:
                        continue
                    if "x-show" in snippet or "x-cloak" in snippet:
                        continue
                    self.fail(
                        f"{path} : empty-state brut sans partial partagé : {match.group(0)!r}"
                    )

    def test_empty_state_partial_supports_dialog_open_cta(self) -> None:
        source = template_source("components/ui/empty_state.html")
        self.assertIn("cta_button_dialog_open", source)
        self.assertIn("data-dialog-open", source)

    def test_staff_css_mirrors_client_page_head_homogeneity(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".portal-page--staff .portal-page-intro", css)
        self.assertIn(".portal-page--client .portal-page-intro", css)

    def test_portal_core_focus_selector_skips_bem_children(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('[class*="-focus"]:not([class*="__"])', css)

    def test_portal_core_flattens_nested_surfaces_inside_list_section_only(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".portal-page-surface.ui-list-section :is(", css)
        for marker in (
            ".atelier-worklist",
            ".staff-data-list",
            ".atelier-operation-row",
            ".ui-mobile-order-card",
            ".ui-list-command",
            ".ui-list-results",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, css)
        for marker in (
            ".staff-order-focus",
            ".staff-customer-workspace",
            ".workflow-shell",
        ):
            with self.subTest(marker=marker):
                self.assertNotIn(
                    f".portal-page-surface.ui-list-section :is(\n  {marker}",
                    css,
                )
        # Champ recherche planches = contrôle interactif : border + focus brand.
        flatten_block = css.split(".portal-page-surface.ui-list-section :is(", 1)[1].split(
            ") {", 1
        )[0]
        self.assertNotIn(".gang-sheet-search", flatten_block)
        self.assertIn(".portal-page-surface .gang-sheet-search:focus-within", css)
        self.assertIn("0 0 0 3px var(--field-focus-ring)", css)
        self.assertIn("outline: none !important", css)
        self.assertIn(
            ".portal-page-surface .gang-sheet-search :is(input, input:focus, input:focus-visible)",
            css,
        )

    def test_staff_dashboard_uses_page_head_without_legacy_head_wrapper(self) -> None:
        source = staff_dashboard_source()
        self.assertIn("page_head.html", source)
        self.assertNotIn("atelier-dashboard-head", source)

    def test_staff_dashboard_does_not_surface_next_action_banner(self) -> None:
        source = staff_dashboard_source()
        self.assertNotIn("atelier-next-action", source)
        self.assertNotIn("Prochain geste", source)

    def test_staff_order_projects_list_uses_ui_list_section(self) -> None:
        source = template_source("portal/staff/order_projects_list.html")
        self.assertIn("portal-page-surface ui-list-section", source)

    def test_staff_focus_pages_surface_contract(self) -> None:
        focus_markers = {
            "portal/staff/order_detail.html": "staff-order-detail-identity",
            "portal/staff/order_project_detail.html": "staff-project-detail-identity",
            "portal/staff/customers/detail.html": "staff-customer-focus",
            "portal/staff/access_requests/detail.html": "staff-access-detail-identity",
        }
        surface_counts = {
            "portal/staff/order_detail.html": 1,
            "portal/staff/order_project_detail.html": 2,
            "portal/staff/customers/detail.html": 2,
            "portal/staff/access_requests/detail.html": 2,
        }
        for path, expected_surfaces in surface_counts.items():
            with self.subTest(path=path):
                source = template_source(path)
                self.assertEqual(
                    expected_surfaces,
                    len(re.findall(r"<section[^>]*portal-page-surface", source)),
                    f"{path} : nombre de sections portal-page-surface inattendu",
                )
        for path, marker in focus_markers.items():
            with self.subTest(path=path, marker=marker):
                source = template_source(path)
                surface_index = source.index("portal-page-surface")
                focus_index = source.index(marker)
                self.assertGreater(focus_index, surface_index, f"{path} : focus hors surface")

    def test_staff_order_detail_matches_dashboard_page_head_layout(self) -> None:
        source = template_source("portal/staff/order_detail.html")
        self.assertIn("page_head.html", source)
        self.assertIn("page_head_actions/staff_order_detail.html", source)
        self.assertIn("staff-order-focus", source)
        self.assertNotIn("atelier-next-action", source)
        self.assertNotIn("Prochain geste", source)
        identity_index = source.index("staff-order-detail-identity")
        workflow_index = source.index("staff-order-detail-surface")
        stack_index = source.index("staff-order-detail-stack")
        self.assertLess(source.index("page_head.html"), workflow_index)
        self.assertLess(workflow_index, identity_index)
        self.assertLess(identity_index, stack_index)

    def test_staff_access_detail_matches_dashboard_next_action_layout(self) -> None:
        source = template_source("portal/staff/access_requests/detail.html")
        identity_index = source.index("staff-access-detail-identity")
        workflow_index = source.index("staff-access-detail-surface")
        self.assertLess(identity_index, workflow_index)
        self.assertIn("atelier-next-action", source)
        self.assertIn("Traiter la demande", source)

    def test_staff_order_project_detail_splits_identity_and_items(self) -> None:
        source = template_source("portal/staff/order_project_detail.html")
        identity_index = source.index("staff-project-detail-identity")
        items_index = source.index("staff-project-detail-surface")
        self.assertLess(identity_index, items_index)
        self.assertNotIn('class="staff-project-focus"', source)
        self.assertNotIn("product-list-card", source)

    def test_staff_drive_sync_panel_avoids_legacy_product_cards(self) -> None:
        source = template_source("portal/staff/panels/drive_sync.html")
        self.assertIn("drive-sync-row", source)
        self.assertNotIn("product-list-card", source)

    def test_staff_dashboard_batch_print_actions_are_visible_buttons(self) -> None:
        source = staff_dashboard_source()
        self.assertIn("Tout cocher", source)
        self.assertIn("Imprimer le lot", source)
        self.assertIn("en attente", source)
        self.assertNotIn("Cocher l’aperçu", source)
        self.assertNotIn("aperçu", source)
        self.assertNotIn("Tout désélectionner", source)
        self.assertNotIn("Imprimer tous (", source)
        self.assertNotIn("Imprimer tous les OF non imprimés", source)
        self.assertNotIn("Sélectionner tous les OF imprimables", source)
        self.assertNotIn("Autres impressions", source)
        self.assertNotIn("atelier-worklist__batch-more", source)

    def test_staff_billing_statements_use_shared_empty_state(self) -> None:
        source = template_source("portal/staff/customers/_billing_statements.html")
        self.assertIn("empty_state.html", source)
        self.assertNotIn("billing-statement-empty", source)

    def test_portal_core_resets_atelier_dashboard_legacy_grid(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".portal-page.atelier-dashboard", css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", css)
        self.assertIn(".atelier-next-action", css)

    def test_portal_staff_resets_atelier_dashboard_legacy_grid(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".portal-page.atelier-dashboard", css)
        self.assertIn("grid-column: 1 / -1 !important", css)

    def test_staff_list_alerts_use_mb4_before_surface(self) -> None:
        for path in (
            "portal/staff/orders_list.html",
            "portal/staff/email_templates/edit.html",
            "portal/client/order_project_form.html",
            "portal/client/gang_sheets/create_order_project.html",
        ):
            with self.subTest(path=path):
                source = template_source(path)
                if "alert" not in source:
                    continue
                surface_index = source.index("portal-page-surface")
                alert_index = source.index("alert")
                self.assertLess(alert_index, surface_index, f"{path} : alerte dans la surface")
                self.assertIn("mb-4", source[:surface_index], f"{path} : alerte sans mb-4")

    def test_list_filter_pages_use_shared_ui_list_tabs(self) -> None:
        for path in (
            "portal/staff/access_requests/list.html",
            "portal/staff/orders_list.html",
        ):
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn("ui_list_tabs", source)
                self.assertNotIn("atelier-worklist__tab", source)
                self.assertNotIn("access-request-status", source)
                self.assertNotIn("atelier-operations-tab", source)

    def test_list_tabs_partial_exposes_homogeneous_markers(self) -> None:
        source = template_source("components/ui/list_tabs.html")
        for marker in (
            'class="ui-list-tabs',
            "ui-selection-rail--horizontal",
            "ui-list-tabs__tab",
            "ui-selection-control",
            "ui-list-tabs__label",
            "ui-list-tabs__count",
            'role="tablist"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

    def test_portal_core_styles_ui_list_tabs(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("/* v17 — Onglets / filtres de listes homogènes", css)
        self.assertIn("min-height: var(--ui-action-min-h)", css)
        self.assertIn(".ui-selection-control:is(", css)
        list_tabs = css.split("v17 — Onglets / filtres", 1)[1].split(
            "v114 — Onglets workflow", 1
        )[0]
        self.assertNotIn(".ui-list-tabs__tab.is-active", list_tabs)

    def test_client_dashboard_uses_single_content_surface(self) -> None:
        source = template_source("portal/client/dashboard.html")
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-client.css").read_text(
            encoding="utf-8"
        )
        self.assertEqual(source.count("client-dashboard-surface"), 2)
        self.assertIn("{% if not memberships %}", source)
        self.assertIn("client-dashboard-section", source)
        self.assertLess(
            source.index("client-dashboard-surface"),
            source.index("client-dashboard-palier"),
        )
        self.assertLess(
            source.index("client-dashboard-palier"),
            source.index("client-dashboard-focus"),
        )
        self.assertLess(
            source.index("client-dashboard-focus"),
            source.index("client-dashboard-section"),
        )
        self.assertIn("v123 — Dashboard client", css)
        self.assertIn(
            "client-dashboard .client-dashboard-surface .client-dashboard-focus",
            css,
        )
        self.assertIn("@layer utilities", css)
        core = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            ".portal-page-surface .client-dashboard-focus",
            core,
        )
        self.assertIn(":not(.client-dashboard-focus)", core)

    def test_list_pages_use_ui_list_section(self) -> None:
        for path in (
            "portal/client/orders_list.html",
            "portal/client/order_projects_list.html",
            "portal/client/gang_sheets/list.html",
            "portal/staff/dashboard.html",
            "portal/staff/orders_list.html",
            "portal/staff/order_projects_list.html",
            "portal/staff/access_requests/list.html",
            "portal/staff/operations/index.html",
            "portal/staff/customers/list.html",
            "portal/staff/email_templates/list.html",
            "portal/staff/machines/index.html",
        ):
            with self.subTest(path=path):
                if path == "portal/staff/dashboard.html":
                    source = staff_dashboard_source()
                else:
                    source = template_source(path)
                self.assertIn("portal-page-surface ui-list-section", source)

    def test_gang_sheet_list_uses_homogeneous_filter_tabs(self) -> None:
        source = template_source("portal/client/gang_sheets/list.html")
        self.assertIn('class="ui-list-tabs', source)
        self.assertNotIn("gang-sheet-filters", source)

    def test_staff_focus_alerts_live_outside_page_surface(self) -> None:
        for path in (
            "portal/staff/order_detail.html",
            "portal/staff/access_requests/detail.html",
        ):
            with self.subTest(path=path):
                source = template_source(path)
                surface_index = source.index("portal-page-surface")
                alert_index = source.index("alert")
                self.assertLess(alert_index, surface_index, f"{path} : alerte dans la surface")

    def test_default_volume_discounts_exposes_two_surfaces(self) -> None:
        source = template_source("portal/staff/customers/default_volume_discounts.html")
        self.assertEqual(source.count("portal-page-surface"), 2)
        self.assertIn("volume-discount-settings-surface", source)
        self.assertIn("volume-nudge-copy-surface", source)
        self.assertIn("font-display", source)
        self.assertIn("volume-nudge-copy", source)
        self.assertNotIn("volume-tier-empty", source)

    def test_staff_list_tabs_follow_command_tabs_results_pattern(self) -> None:
        source = template_source("portal/staff/access_requests/list.html")
        command_index = source.index("access-request-command")
        tabs_index = source.index("ui_list_tabs")
        results_index = source.index("access-request-results")
        self.assertLess(command_index, tabs_index)
        self.assertLess(tabs_index, results_index)

        operations_index = template_source("portal/staff/operations/index.html")
        operations_workspace = template_source("portal/staff/operations/_workspace.html")
        focus_card = template_source("portal/staff/operations/_focus_card.html")
        scan_index = operations_index.index("atelier-operations-scan-bar")
        panel_index = operations_index.index("atelier-operations-panel")
        self.assertLess(scan_index, panel_index)
        self.assertIn("focus_row", operations_workspace)
        self.assertIn("ui_list_tabs", focus_card)
        self.assertNotIn("atelier-operations-results", operations_workspace)

    def test_portal_core_styles_list_tabs_placement(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("/* v20 — Placement homogène list tabs", css)
        self.assertIn("/* v21 — File / Pilotage Atelier", css)
        self.assertIn("/* v26 — Listes (ui-list-section)", css)
        self.assertNotIn("/* v25 — Aplatissement visible", css)
        self.assertNotIn(".portal-page-surface .atelier-worklist__legend {\n  display: none", css)
        self.assertIn(".atelier-dashboard-surface > .ui-list-tabs", css)
        self.assertIn(".atelier-operations-panel > .ui-list-tabs", css)

    def test_pilotage_flat_styles_live_in_operations_component(self) -> None:
        css_path = Path(settings.BASE_DIR) / "static_src/css/components/atelier-operations.css"
        css = css_path.read_text(encoding="utf-8")
        for marker in (
            ".atelier-operation-row__workflow",
            ".atelier-operation-workflow__link",
            ".atelier-operations-focus__tabs",
            ".atelier-operations-focus",
            ".atelier-operations-scan-bar",
            ".atelier-operations-scan__input",
            ".atelier-operation-shipping-form:not([open]) > form",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, css)

    def test_client_order_panels_avoid_legacy_panel_wrapper(self) -> None:
        for path in CLIENT_ORDER_PANELS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertNotIn('class="panel ', source)
                self.assertIn("client-order-panel", source)

    def test_client_order_inspection_uses_shared_kpi_pattern(self) -> None:
        source = template_source("portal/client/panels/inspection.html")
        self.assertIn("ui_kpi_grid", source)
        self.assertNotIn('article class="card"', source)
        self.assertNotIn("panel-head", source)

    def test_b2b_configurator_partials_avoid_legacy_card_wrapper(self) -> None:
        for path in (
            "portal/client/partials/order_project_items.html",
            "portal/client/partials/order_project_fields.html",
        ):
            with self.subTest(path=path):
                source = template_source(path)
                self.assertNotIn('class="card b2b-', source)

    def test_client_checkout_avoids_nested_product_panel(self) -> None:
        source = template_source("portal/client/checkout.html")
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-client.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("client-checkout-intro", source)
        self.assertNotIn("product-panel", source)
        self.assertIn("client-checkout-surface", source)
        self.assertIn("v140 — Checkout legacy", css)
        self.assertIn(
            "client-checkout-surface .product-checkout-card",
            css,
        )

    def test_client_order_project_detail_reuses_order_facts_chrome(self) -> None:
        source = template_source("portal/client/order_project_detail.html")
        facts = template_source("portal/client/partials/order_project_facts.html")
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-client.css").read_text(
            encoding="utf-8"
        )
        self.assertEqual(1, len(re.findall(r"<section[^>]*portal-page-surface", source)))
        self.assertIn("client-order-project-identity", facts)
        self.assertIn(">Date<", facts)
        self.assertIn(">Référence<", facts)
        self.assertIn(">Règlement<", facts)
        self.assertIn("client-order-project-stack", source)
        self.assertNotIn("stack-lg", source)
        self.assertIn(
            ":is(.client-order-detail, .client-order-project-detail) .client-order-summary__facts",
            css,
        )
        self.assertIn("v140 — Rythme Operate partagé", css)
        self.assertIn("b2b-order-start-surface", css)

    def test_staff_atelier_views_avoid_legacy_visual_patterns(self) -> None:
        for path in STAFF_ATELIER_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                for pattern, label in LEGACY_PATTERNS:
                    self.assertIsNone(re.search(pattern, source), f"{path} : reliquat {label}")
                self.assertNotIn('class="card ', source)
                self.assertNotIn('class="panel ', source)
                self.assertNotIn("gang-sheet-create-card", source)
                self.assertNotIn("machine-fleet-empty", source)

    def test_staff_workflow_panels_use_semantic_hero_header(self) -> None:
        for path in STAFF_PANEL_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn("workflow-panel", source)
                self.assertIn('<header class="workflow-panel__hero', source)
                self.assertNotIn('<div class="workflow-panel__hero', source)

    def test_staff_configuration_pages_use_list_section_or_focus_contract(self) -> None:
        for path in ("portal/staff/email_templates/list.html", "portal/staff/machines/index.html"):
            with self.subTest(path=path):
                self.assertIn("ui-list-section", template_source(path))
        gang_settings = template_source("portal/staff/gang_sheets/settings.html")
        self.assertIn("gang-settings-surface", gang_settings)
        self.assertIn("font-display", gang_settings)
        machines_fleet = template_source("portal/staff/machines/_fleet_content.html")
        self.assertIn("font-display text-lg", machines_fleet)
        self.assertIn("machine-fleet-summary__rule", machines_fleet)

    def test_staff_machines_use_shared_empty_state(self) -> None:
        source = template_source("portal/staff/machines/_fleet_content.html")
        self.assertGreaterEqual(source.count("empty_state.html"), 2)
        self.assertNotIn("machine-fleet-empty", source)

    def test_staff_machines_use_orders_list_table_and_create_dialog(self) -> None:
        source = template_source("portal/staff/machines/_fleet_content.html")
        index = template_source("portal/staff/machines/index.html")
        self.assertIn("ui-data-table", source)
        self.assertIn("ui-table-shell", source)
        self.assertIn("ui-mobile-order-card", source)
        self.assertIn("machine-create-dialog", source)
        self.assertIn("machine-fleet-dialog", source)
        self.assertIn("page_head_actions/staff_machines.html", index)
        self.assertNotIn("machine-register-row", source)

    def test_portal_staff_flattens_machine_fleet_and_gang_settings(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("v30 — Réglages planches staff", css)
        self.assertIn(".gang-settings-surface", css)
        self.assertIn("v31 — Remises volume", css)
        self.assertIn(".volume-discount-settings-surface", css)
        self.assertIn("v32 — Parc machines", css)
        self.assertIn(".machine-fleet-surface", css)

    def test_staff_volume_discounts_use_orders_list_table_and_create_dialog(self) -> None:
        source = template_source("portal/staff/customers/default_volume_discounts.html")
        self.assertIn("ui-data-table", source)
        self.assertIn("ui-table-shell", source)
        self.assertIn("ui-mobile-order-card", source)
        self.assertIn("volume-tier-create-dialog", source)
        self.assertIn("volume-discount-dialog", source)
        self.assertIn("page_head_actions/staff_volume_discounts.html", source)
        self.assertNotIn("volume-tier-create-card", source)
        self.assertNotIn("volume-tier-list", source)

    def test_staff_customer_detail_uses_orders_list_table_and_create_dialogs(self) -> None:
        source = template_source("portal/staff/customers/detail.html")
        register = template_source("portal/staff/customers/_volume_discount_tier_register.html")
        statements = template_source("portal/staff/customers/_billing_statements.html")
        combined = f"{source}\n{register}\n{statements}"
        self.assertIn("_volume_discount_tier_register.html", source)
        self.assertIn("ui-data-table", combined)
        self.assertIn("ui-mobile-order-card", combined)
        self.assertIn("volume-tier-create-dialog", register)
        self.assertIn("billing-statement-create-dialog", statements)
        self.assertNotIn("volume-tier-list", combined)
        self.assertNotIn("volume-tier-create-inline", combined)
        self.assertNotIn("billing-statement-row", statements)
        self.assertNotIn("_volume_discount_tier_row.html", source)

    def test_staff_atelier_configuration_surfaces_use_flat_typography(self) -> None:
        checks = {
            "portal/staff/email_templates/list.html": (
                "font-display text-lg",
                "email-template-surface",
            ),
            "portal/staff/settings/branding.html": (
                "font-display text-lg",
                "brand-settings-surface",
            ),
        }
        for path, (typography, surface_class) in checks.items():
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn(typography, source)
                self.assertIn(surface_class, source)

    def test_staff_customer_detail_uses_shared_empty_state_for_volume_tiers(self) -> None:
        source = template_source("portal/staff/customers/_volume_discount_tier_register.html")
        self.assertIn("empty_state.html", source)
        self.assertNotIn("volume-tier-empty", source)

    def test_portal_staff_flattens_remaining_atelier_configuration_pages(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("v33 — Modèles e-mails", css)
        self.assertIn(".email-template-surface", css)
        self.assertIn(".brand-settings-surface", css)
        self.assertIn(".email-template-editor-surface", css)
        self.assertIn("v63 — Fiche client", css)
        self.assertIn(".staff-customer-detail-page .volume-discount-dialog", css)

    def test_staff_production_panel_uses_flat_operator_typography(self) -> None:
        source = template_source("portal/staff/panels/production.html")
        self.assertIn("font-display text-lg", source)
        self.assertIn("operator-machine", source)
        self.assertIn('<header class="workflow-panel__hero', source)

    def test_portal_staff_flattens_production_panel_in_order_detail(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("v34 — Panneau Production", css)
        self.assertIn(".staff-order-detail-stack .operator-machine", css)
        self.assertIn(".staff-order-detail-stack .gang-sheet-production-list article", css)

    def test_staff_order_detail_surface_flattens_nested_borders(self) -> None:
        source = template_source("portal/staff/order_detail.html")
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("staff-order-detail-identity", source)
        self.assertIn("page_head.html", source)
        self.assertIn("staff-order-focus__facts", source)
        self.assertNotIn("atelier-next-action", source)
        self.assertIn("v35 — Fiche commande Atelier", css)
        self.assertIn("v39 — Même plan que dashboard", css)
        self.assertIn("v41 — Passe homogène fiches focus Atelier", css)
        self.assertIn("v118 — Verrou pixel fiche commande", css)
        self.assertIn("v119 — Bat @layer utilities", css)
        self.assertIn(".staff-order-detail-page .staff-order-detail-surface", css)
        self.assertIn(".staff-order-detail-stack .empty-state", css)
        self.assertIn(".staff-order-detail-stack .atelier-inspection", css)
        self.assertIn("--portal-inner-chrome: empty", css)
        self.assertIn("--portal-inner-chrome: inspection", css)

    def test_staff_customer_detail_surface_flattens_nested_borders(self) -> None:
        source = template_source("portal/staff/customers/detail.html")
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("staff-customer-detail-surface", source)
        self.assertIn("staff-customer-detail-identity", source)
        self.assertIn("page_head.html", source)
        self.assertIn("staff-customer-focus__facts", source)
        self.assertIn("staff-customer-workspace-surface", source)
        self.assertIn("v120 — Verrou pixel fiche compte", css)
        self.assertIn("v121 — Workspace compte", css)
        self.assertIn(".staff-customer-detail-page .staff-customer-detail-surface", css)
        self.assertIn(
            "staff-customer-detail-surface > header.staff-customer-focus"
            ".staff-customer-detail-identity",
            css,
        )
        self.assertIn("staff-customer-workspace-surface .empty-state", css)
        self.assertIn("staff-customer-workspace__section .empty-state", css)
        self.assertIn("@layer utilities", css)

    def test_client_order_detail_surface_matches_staff_chrome(self) -> None:
        source = template_source("portal/client/order_detail.html")
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-client.css").read_text(
            encoding="utf-8"
        )
        core = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertEqual(1, len(re.findall(r"<section[^>]*portal-page-surface", source)))
        self.assertIn("client-order-detail-identity", source)
        self.assertIn("client-order-detail-stack", source)
        self.assertIn("page_head.html", source)
        self.assertIn("page_head_actions/client_order_detail.html", source)
        self.assertIn("v114 — Fiche commande client", css)
        self.assertIn("v138 — Verrou pixel fiche commande client", css)
        self.assertIn(".client-order-detail .client-order-detail-surface", css)
        self.assertIn(".client-order-detail-stack .empty-state", css)
        self.assertIn(".client-order-detail-stack .client-order-panel", css)
        self.assertIn("--portal-inner-chrome: client-panel", css)
        self.assertIn(
            "client-order-detail-surface .client-order-detail-stack > .ui-workflow-shell.card",
            css,
        )
        self.assertIn("@layer utilities", css)
        self.assertIn(".portal-page-surface .workflow-tab-rail", core)
        identity_index = source.index("client-order-detail-identity")
        surface_index = source.index("client-order-detail-surface")
        stack_index = source.index("client-order-detail-stack")
        self.assertLess(surface_index, identity_index)
        self.assertLess(identity_index, stack_index)

    def test_account_profile_surface_matches_portal_chrome(self) -> None:
        source = template_source("portal/profile.html")
        focus = template_source("portal/partials/profile_staff_focus.html")
        staff_css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-staff.css").read_text(
            encoding="utf-8"
        )
        client_css = (
            Path(settings.BASE_DIR) / "static_src/css/entries/portal-client.css"
        ).read_text(encoding="utf-8")
        core = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertEqual(4, len(re.findall(r"<section[^>]*portal-page-surface", source)))
        self.assertIn("staff-customer-detail-surface", source)
        self.assertIn("staff-customer-detail-identity", focus)
        self.assertNotIn("staff-profile-surface", source)
        self.assertNotIn("staff-profile-stack", source)
        self.assertIn("client-profile-page", source)
        self.assertIn("profile_client_focus.html", source)
        self.assertIn("v125 — Profil client", client_css)
        self.assertIn(".staff-customer-detail-identity", staff_css)
        profile_identity = (
            ".portal-page-surface.staff-customer-detail-surface > "
            "header.staff-customer-focus.staff-customer-detail-identity"
        )
        self.assertIn(f"staff-profile-page {profile_identity}", staff_css)
        self.assertIn("v122 — Profil staff", staff_css)
        self.assertIn(f"client-profile-page {profile_identity}", client_css)
        self.assertIn(".portal-page-surface .account-profile-panel", core)
        self.assertIn("--portal-inner-chrome: profile-panel", core)
        self.assertLess(
            source.index("staff-customer-detail-surface"),
            source.index("data-customer-workspace"),
        )
        self.assertIn("customer-account-workspace.css", client_css)
