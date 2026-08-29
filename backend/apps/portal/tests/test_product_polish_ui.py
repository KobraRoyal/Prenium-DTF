from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE_DIR = Path(settings.BASE_DIR)
CSS_DIR = BASE_DIR / "static_src/css"
TEMPLATES_DIR = BASE_DIR / "templates"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def portal_surface_css() -> str:
    """CSS réellement chargé par le portail après le split core / client / staff / prospect."""
    return "\n".join(
        [
            source(CSS_DIR / "entries" / "portal-core.css"),
            source(CSS_DIR / "entries" / "portal.css"),
            source(CSS_DIR / "entries" / "prospect.css"),
            source(CSS_DIR / "components" / "prospect-journey.css"),
            source(CSS_DIR / "components" / "product-polish.css"),
        ]
    )


class ProductPolishUITests(SimpleTestCase):
    def test_product_polish_is_the_last_portal_component_before_tailwind(self) -> None:
        core = source(CSS_DIR / "entries/portal-core.css")
        aggregator = source(CSS_DIR / "entries/portal.css")
        polish_import = '@import "../components/product-polish.css";'
        last_import = '@import "../components/prospect-journey.css";'

        self.assertIn(polish_import, core)
        self.assertIn(last_import, aggregator)
        self.assertLess(core.index(polish_import), core.index("@tailwind base"))
        self.assertEqual(aggregator.rfind("@import"), aggregator.index(last_import))

        polish = source(CSS_DIR / "components/product-polish.css")
        self.assertIn("@layer utilities", polish)
        self.assertIn("--product-bg: var(--bg)", polish)
        self.assertIn("--product-panel: var(--surface)", polish)
        self.assertIn("--product-ink: var(--ink)", polish)
        self.assertIn("--product-accent: var(--brand)", polish)
        self.assertIn("--product-polish-radius: var(--radius)", polish)
        self.assertIn("body.product-shell :is(.badge, .ui-inline-flag)", polish)
        self.assertIn("body.product-shell .gang-sheet-card", polish)
        self.assertIn("body.product-shell .ui-kpi-card::before", polish)
        self.assertIn("body.product-shell .staff-order-focus__next", polish)
        self.assertIn("body.product-shell .product-checkout-step", polish)
        self.assertIn("body.product-shell :is(.checkout-dropzone-dui, .dropzone)", polish)
        self.assertIn(".checkout-dui-input", polish)
        self.assertIn("@media (max-width: 39.99rem)", polish)
        # linear-gradient OK pour damier / fade sticky actions ; pas de glow radial décoratif.
        self.assertNotIn("radial-gradient(", polish)

    def test_shared_foundations_own_buttons_tables_and_responsive_cards(self) -> None:
        buttons = source(CSS_DIR / "components/buttons.css")
        shell = source(CSS_DIR / "components/shell.css")
        legacy = source(CSS_DIR / "components/product-shell.css")
        polish = source(CSS_DIR / "components/product-polish.css")

        self.assertIn(".dui-btn-secondary", buttons)
        self.assertIn(":is(.ui-btn-ghost, .dui-btn-ghost)", buttons)
        self.assertIn(".ui-data-table thead", shell)
        self.assertIn(".ui-data-card", shell)
        self.assertIn(".ui-mobile-order-card", shell)
        self.assertIn(".ui-list-pagination", shell)
        self.assertIn(".ui-list-section", shell)

        for obsolete in [
            "body.product-shell .ui-data-table thead th",
            "body.product-shell .staff-data-card",
            "body.product-shell .ui-mobile-order-card {",
            "body.product-shell .btn-secondary,",
            "body.product-shell .dui-table",
        ]:
            with self.subTest(obsolete=obsolete):
                self.assertNotIn(obsolete, legacy)

        self.assertNotIn("body.product-shell .ui-btn-secondary {", polish)
        self.assertNotIn("body.product-shell .ui-table-shell {", polish)
        self.assertNotIn("body.product-shell .ui-mobile-order-card {", polish)
        self.assertIn(".badge.is-success", polish)
        self.assertIn(".badge.is-warning", polish)
        self.assertIn(".badge.is-danger", polish)

    def test_simple_actions_share_breadcrumb_inspired_underline_motion(self) -> None:
        buttons = source(CSS_DIR / "components" / "buttons.css")
        shell = source(CSS_DIR / "components" / "shell.css")
        core = source(CSS_DIR / "entries" / "portal-core.css")

        for marker in [
            "--ui-simple-underline-color: var(--brand)",
            ".ui-btn-ghost::before",
            "transform: scaleX(0)",
            "transform: scaleX(1)",
            "transform-origin: left center",
            "prefers-reduced-motion: reduce",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, buttons)

        for marker in [
            ".product-profile__trigger-label",
            ".product-nav__more-link strong",
            ".product-profile__action strong",
            ".product-profile__logout > span:last-child",
            "background: var(--brand)",
            "background: var(--danger)",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, shell)

        ghost_hover_selector = """.ui-btn-ghost,
  .dui-btn-ghost
):is(:hover, :focus-visible, :active)"""
        self.assertIn(ghost_hover_selector, core)
        ghost_override = core.split(ghost_hover_selector, 1)[1].split("}", 1)[0]
        self.assertIn("background: transparent !important", ghost_override)
        self.assertIn("border-color: transparent !important", ghost_override)

    def test_navigation_selections_share_the_active_underline_contract(self) -> None:
        buttons = source(CSS_DIR / "components" / "buttons.css")
        core = source(CSS_DIR / "entries" / "portal-core.css")
        staff = source(CSS_DIR / "entries" / "portal-staff.css")
        atelier_operations = source(CSS_DIR / "components" / "atelier-operations.css")
        volume_nudge = source(CSS_DIR / "components" / "volume-nudge-copy.css")
        product_shell = source(CSS_DIR / "components" / "product-shell.css")
        account_workspace = source(
            CSS_DIR / "components" / "customer-account-workspace.css"
        )

        for marker in (
            ".ui-selection-rail--horizontal",
            ":is(.ui-selection-control, .ui-inline-action, .ui-destructive-action)::after",
            "--ui-selection-indicator-color: var(--brand)",
            'aria-current="location"',
            'aria-selected="true"',
            "transform: scaleX(0) !important",
            "transform: scaleX(1) !important",
            "transition: none !important",
            "cursor: pointer",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, buttons)

        self.assertIn("v52 — Autorité finale des filtres", core)
        bridge = core.split("v52 — Autorité finale des filtres", 1)[1].split("/* v29", 1)[0]
        self.assertIn("background: transparent !important", bridge)
        self.assertIn("border-radius: 0 !important", bridge)
        self.assertNotIn("color-mix(in srgb, var(--brand)", bridge)

        list_tabs = core.split("v17 — Onglets / filtres", 1)[1].split(
            "v114 — Onglets workflow", 1
        )[0]
        self.assertIn("min-height: var(--ui-action-min-h)", list_tabs)
        self.assertIn("background: transparent", list_tabs)
        self.assertNotIn(".ui-list-tabs__tab:hover", list_tabs)
        self.assertNotIn(".ui-list-tabs__tab.is-active,", list_tabs)
        list_tab_rule = list_tabs.split(".ui-list-tabs__tab {", 1)[1].split(
            "}", 1
        )[0]
        self.assertNotIn("border-radius: 999px", list_tab_rule)

        workflow_tabs = core.split("v114 — Onglets workflow", 1)[1].split(
            "v20 — Placement homogène", 1
        )[0]
        self.assertIn("min-height: var(--ui-action-min-h)", workflow_tabs)
        self.assertNotIn(".ui-tab-chip:hover", workflow_tabs)
        self.assertNotIn(".ui-tab-chip.is-active", workflow_tabs)

        template_paths = (
            "components/ui/list_tabs.html",
            "components/order/order_tabs.html",
            "components/portal/account_rail.html",
            "portal/client/gang_sheets/list.html",
            "portal/client/gang_sheets/editor.html",
            "portal/staff/customers/default_volume_discounts.html",
            "portal/staff/customers/detail.html",
            "portal/staff/operations/_job_row.html",
        )
        for template_path in template_paths:
            with self.subTest(template_path=template_path):
                template = source(TEMPLATES_DIR / template_path)
                self.assertIn("ui-selection-control", template)
                self.assertIn("ui-selection-rail", template)

        atelier_workflow = source(
            TEMPLATES_DIR / "portal/staff/operations/_job_row.html"
        )
        self.assertIn(
            "atelier-operation-workflow ui-selection-rail "
            "ui-selection-rail--horizontal",
            atelier_workflow,
        )

        obsolete_staff_states = {
            "portal-staff.css": (
                staff,
                (
                    ".volume-nudge-copy__tab.is-active",
                    '.staff-customer-workspace__nav a[aria-current="location"]',
                    '.account-profile-nav a[aria-current="location"]',
                    ".account-profile-nav a:hover",
                ),
            ),
            "atelier-operations.css": (
                atelier_operations,
                (
                    ".atelier-operation-workflow__link:hover",
                    ".atelier-operation-workflow__link.is-active",
                ),
            ),
            "volume-nudge-copy.css": (
                volume_nudge,
                (".volume-nudge-copy__tab.is-active",),
            ),
            "customer-account-workspace.css": (
                account_workspace,
                ('.staff-customer-workspace__nav a[aria-current="location"]',),
            ),
        }
        for stylesheet, (css, obsolete_markers) in obsolete_staff_states.items():
            for marker in obsolete_markers:
                with self.subTest(stylesheet=stylesheet, marker=marker):
                    self.assertNotIn(marker, css)

        atelier_link = atelier_operations.split(
            ".atelier-operation-workflow__link {", 1
        )[1].split("}", 1)[0]
        self.assertNotIn("border-radius", atelier_link)
        self.assertIn("min-height: var(--ui-action-min-h)", atelier_link)
        atelier_surface = atelier_operations.split(
            ".atelier-operations-surface {", 1
        )[1].split("}", 1)[0]
        self.assertIn("grid-template-columns: minmax(0, 1fr)", atelier_surface)
        self.assertIn("min-width: 0", atelier_surface)
        self.assertNotIn(
            ".staff-order-detail-stack .workflow-progress .ui-tab-chip::after",
            product_shell,
        )

    def test_order_lists_keep_buttons_and_details_use_inline_actions(self) -> None:
        buttons = source(CSS_DIR / "components" / "buttons.css")

        for marker in (
            ".ui-inline-action {",
            ".ui-inline-action--control",
            "--ui-underline-color: var(--brand)",
            "font-family: inherit",
            "border-radius: 0 !important",
            ":is(.ui-selection-control, .ui-inline-action, .ui-destructive-action)::after",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, buttons)

        list_templates_and_button_minimums = {
            "components/tables/orders_table.html": 4,
            "components/tables/order_projects_table.html": 2,
            "portal/staff/order_projects_list.html": 1,
        }
        for template_path, minimum in list_templates_and_button_minimums.items():
            with self.subTest(template_path=template_path):
                template = source(TEMPLATES_DIR / template_path)
                self.assertGreaterEqual(template.count("ui-btn ui-btn-secondary"), minimum)
                self.assertNotIn("ui-inline-action", template)

        detail_templates_and_minimums = {
            "portal/client/panels/production.html": 1,
            "portal/client/panels/billing.html": 1,
            "portal/client/panels/uploads.html": 2,
            "portal/staff/order_detail.html": 2,
            "portal/staff/panels/drive_sync.html": 1,
            "portal/staff/panels/uploads.html": 2,
            "portal/staff/panels/inspection.html": 1,
            "portal/staff/panels/production.html": 2,
            "portal/staff/panels/shipping.html": 2,
            "portal/staff/panels/billing.html": 1,
        }
        for template_path, minimum in detail_templates_and_minimums.items():
            with self.subTest(template_path=template_path):
                template = source(TEMPLATES_DIR / template_path)
                self.assertGreaterEqual(template.count("ui-inline-action"), minimum)

    def test_priority_product_templates_have_composed_surfaces(self) -> None:
        client_dashboard = source(TEMPLATES_DIR / "portal/client/dashboard.html")
        atelier_dashboard = source(TEMPLATES_DIR / "portal/staff/dashboard.html")
        login = source(TEMPLATES_DIR / "portal/login.html")

        self.assertIn(
            'components/portal/page_head.html" with breadcrumb_template='
            '"components/portal/breadcrumbs/client_dashboard.html"',
            client_dashboard,
        )
        self.assertNotIn('class="product-eyebrow">Espace client', client_dashboard)
        self.assertIn("portal-page--staff", atelier_dashboard)
        self.assertIn("atelier-dashboard", atelier_dashboard)
        self.assertNotIn('class="product-eyebrow">Production', atelier_dashboard)
        self.assertIn("product-login-card__intro", login)
        self.assertNotIn("product-login-heading", login)
        self.assertNotIn('class="product-eyebrow">Votre espace Prenium', login)
        self.assertIn('id="login-heading"', login)
        self.assertIn("data-submit-loading", login)
        self.assertIn("novalidate", login)
        self.assertIn("data-inline-required", login)
        self.assertIn("ui-form-stack", login)
        self.assertIn("ui-input", login)
        self.assertNotIn("dui-input", login)
        self.assertNotIn("dui-alert", login)

    def test_login_auth_surface_is_a_single_centered_card(self) -> None:
        core = source(CSS_DIR / "entries/portal-core.css")
        login_css = source(CSS_DIR / "components/auth-login.css")
        login = source(TEMPLATES_DIR / "portal/login.html")

        self.assertIn('@import "../components/auth-login.css";', core)
        polish_import = '@import "../components/product-polish.css";'
        auth_import = '@import "../components/auth-login.css";'
        self.assertLess(core.index(polish_import), core.index(auth_import))
        self.assertIn("width: min(100%, 26.5rem)", login_css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", login_css)
        self.assertIn("product-login-password", login_css)
        self.assertIn("grid-template-areas:", login_css)
        self.assertIn('"error error"', login_css)
        self.assertIn('"error error"', core)
        self.assertNotIn("product-login-heading", login_css)
        self.assertIn("product-login-card__intro", login)
        self.assertIn("product-login-password", login)
        self.assertIn("product-login-footer", login)
        self.assertEqual(login.count("product-auth-card"), 1)
        self.assertIn("Mot de passe oublié", login)
        self.assertIn("portal/partials/auth_support.html", login)
        self.assertGreater(core.rfind("product-login-password"), core.index("@tailwind utilities"))

    def test_checkout_and_core_client_views_use_ui_form_contract(self) -> None:
        form_paths = [
            TEMPLATES_DIR / "portal" / "client" / "checkout.html",
            TEMPLATES_DIR / "portal" / "client" / "partials" / "checkout_uploads.html",
            TEMPLATES_DIR / "portal" / "client" / "orders_list.html",
        ]
        alert_paths = [
            TEMPLATES_DIR / "portal" / "client" / "order_detail.html",
            TEMPLATES_DIR / "portal" / "client" / "team.html",
        ]
        forbidden = [
            "dui-alert",
            "dui-input-bordered",
            "dui-form-control",
            "dui-card-body",
            "dui-card-title",
            "dui-divider",
            "dui-table",
            "dui-checkbox",
        ]

        for path in form_paths:
            markup = source(path)
            with self.subTest(path=path.name):
                self.assertIn("ui-input", markup)
                for marker in forbidden:
                    self.assertNotIn(marker, markup)

        for path in alert_paths:
            markup = source(path)
            with self.subTest(path=path.name):
                self.assertIn("alert--", markup)
                for marker in forbidden:
                    self.assertNotIn(marker, markup)

        summary = source(TEMPLATES_DIR / "portal" / "client" / "partials" / "checkout_summary.html")
        checkout = source(TEMPLATES_DIR / "portal" / "client" / "checkout.html")
        uploads = source(TEMPLATES_DIR / "portal" / "client" / "partials" / "checkout_uploads.html")
        self.assertIn("ui-checkbox-row", summary)
        self.assertIn("ui-form-stack", summary)
        self.assertNotIn("opacity-", summary)
        self.assertNotIn("product-section-kicker", checkout)
        self.assertIn("ui-field-help", checkout)
        self.assertNotIn("opacity-", checkout)
        self.assertNotIn("opacity-", uploads)
        self.assertIn("components/ui/empty_state.html", uploads)
        for marker in forbidden:
            self.assertNotIn(marker, summary)

    def test_prospect_tunnel_steps_avoid_legacy_dui_form_primitives(self) -> None:
        form_paths = [
            TEMPLATES_DIR / "prospects" / "step1.html",
            TEMPLATES_DIR / "prospects" / "step2.html",
            TEMPLATES_DIR / "portal" / "access" / "invitation_accept.html",
        ]
        summary_paths = [
            TEMPLATES_DIR / "prospects" / "step3.html",
        ]
        forbidden = [
            "dui-alert",
            "dui-input-bordered",
            "dui-form-control",
            "dui-select",
            "dui-textarea",
            "dui-checkbox",
        ]
        for path in form_paths:
            markup = source(path)
            with self.subTest(path=path.name):
                self.assertIn("ui-input", markup)
                if path.name.startswith("step"):
                    self.assertIn("product-field-input", markup)
                    self.assertNotIn("checkout-dui-input", markup)
                for marker in forbidden:
                    self.assertNotIn(marker, markup)

        for path in summary_paths:
            markup = source(path)
            with self.subTest(path=path.name):
                self.assertIn("ui-form-stack", markup)
                for marker in forbidden:
                    self.assertNotIn(marker, markup)

    def test_portal_entrypoint_redefines_product_tokens_from_global_palette(self) -> None:
        entry = portal_surface_css()
        shell = source(CSS_DIR / "components" / "shell.css")

        for token in [
            "--product-bg: var(--bg)",
            "--product-accent: var(--brand)",
            "--product-line: var(--line)",
        ]:
            with self.subTest(token=token):
                self.assertIn(token, entry)

        self.assertIn("text-decoration-color: var(--brand-strong)", shell)
        self.assertIn("box-shadow: none !important", shell)
        self.assertIn(".checkout-panel-divider", shell)
        self.assertIn(".staff-customer-focus", shell)

    def test_portal_entrypoint_neutralizes_prospect_brutalist_runtime(self) -> None:
        entry = portal_surface_css()

        for marker in [
            "body.prospect-journey-page",
            "body.prospect-tunnel-page",
            "--journey-ink: var(--ink)",
            "--journey-paper: var(--bg)",
            "body.prospect-journey-page .prospect-journey__frame",
            "body.prospect-journey-page .prospect-journey__rail",
            "box-shadow: none !important",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, entry)

    def test_portal_entrypoint_styles_prospect_product_field_inputs(self) -> None:
        entry = portal_surface_css()

        for marker in [
            ".product-field-input",
            "border-radius: var(--radius-sm)",
            "0 0 0 3px var(--field-focus-ring)",
            "--field-focus-ring",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, entry)

    def test_portal_entrypoint_neutralizes_product_shell_card_shadows(self) -> None:
        entry = portal_surface_css()

        for marker in [
            'html[data-theme="prenium"] body.product-shell',
            ".staff-project-focus",
            ".staff-project-items",
            ".gang-editor__header",
            "box-shadow: none !important",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, entry)

    def test_portal_entrypoint_overrides_app_legacy_portal_shell_brutalism(self) -> None:
        entry = portal_surface_css()
        legacy = source(CSS_DIR / "legacy" / "app-legacy.css")

        self.assertIn("body.landing-saas.portal-shell .card", legacy)
        self.assertIn("box-shadow: 8px 8px 0 #0b0b0b", legacy)

        for marker in [
            "body.landing-saas.portal-shell.product-shell",
            "écrase app-legacy.css",
            ".portal-login-card",
            "tbody tr:hover",
            ".app-header.product-header",
            ".alert--warning",
            ".ui-input:focus",
            ".ui-btn-ghost",
            "filter: none !important",
            "tr.ui-row-warning",
            "tbody tr:hover",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, entry)

    def test_marketing_entrypoint_aligns_conversion_tokens_with_light_palette(self) -> None:
        entry = source(CSS_DIR / "entries" / "marketing.css")

        for marker in [
            "body.landing-conversion-page",
            "--conversion-ink: var(--ink)",
            "--conversion-paper: var(--bg)",
            "--conversion-line: var(--line)",
            "box-shadow: none !important",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, entry)

    def test_tracking_action_is_owned_by_shipping_panel_only(self) -> None:
        detail = source(TEMPLATES_DIR / "portal/client/order_detail.html")
        shipping = source(TEMPLATES_DIR / "portal/client/panels/shipping.html")

        self.assertNotIn("client-order-summary__tracking", detail)
        self.assertNotIn("Suivre le colis", detail)
        self.assertIn("client-shipment-card__tracking", shipping)
        self.assertIn("Suivre mon colis", shipping)
        self.assertIn('target="_blank" rel="noopener noreferrer"', shipping)

    def test_studio_dialog_uses_b2b_dialog_head_instead_of_hidden_eyebrow(self) -> None:
        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")
        studio_entry = source(CSS_DIR / "entries/studio.css")

        self.assertNotIn("product-eyebrow", editor)
        self.assertIn('id="gang-asset-dialog-title">Importer', editor)
        self.assertIn("b2b-dialog-head", editor)
        self.assertIn(".gang-asset-modal-form__controls", studio_entry)

    def test_marketing_entry_neutralizes_agency_defaults_on_conversion_pages(self) -> None:
        entry = source(CSS_DIR / "entries/marketing.css")

        self.assertIn(
            "body.ui-marketing-body.landing-conversion-page:not(.portal-shell):not(.prospect-tunnel-page)",
            entry,
        )
        self.assertIn("Neutralise les défauts agency-*", entry)

    def test_portal_core_card_chrome_uses_where_so_nested_panels_flatten(self) -> None:
        core = source(CSS_DIR / "entries/portal-core.css")
        chrome = core.split("écrase app-legacy.css", 1)[1].split("/* v111", 1)[0]
        selector = chrome.split("html[data-theme", 1)[1]
        detail = source(CSS_DIR / "components/client-order-detail.css")
        uploads = source(TEMPLATES_DIR / "portal/client/panels/uploads.html")

        self.assertIn(":where(", selector)
        self.assertNotIn(":is(", selector)
        self.assertIn(".portal-page .portal-page-surface .client-order-panel", core)
        self.assertIn(".portal-page .portal-page-surface .workflow-panel-target", core)
        self.assertIn(".client-order-panel--uploads", detail)
        self.assertIn("ui-inline-action ui-inline-action--control", uploads)
        self.assertNotIn("Recommander", uploads)
        self.assertEqual(uploads.count("ui-inline-action ui-inline-action--control"), 2)

        actions = source(
            TEMPLATES_DIR / "components/portal/page_head_actions/client_order_detail.html"
        )
        self.assertIn("Recommander", actions)
        self.assertIn("client-order-reorder", actions)
        self.assertIn("ui-btn ui-btn-secondary", actions)

    def test_client_and_staff_order_tabs_share_the_flat_scrollable_rail(self) -> None:
        detail = source(CSS_DIR / "components/client-order-detail.css")
        client = source(CSS_DIR / "entries" / "portal-client.css")
        core = source(CSS_DIR / "entries" / "portal-core.css")
        order_tabs = source(TEMPLATES_DIR / "components/order/order_tabs.html")

        self.assertNotIn("workflow-tab-group__chips--flat", detail)
        self.assertNotIn(
            ".client-order-detail .workflow-tab-group__chips--flat",
            client,
        )
        self.assertIn(".portal-order-tabs > .ui-order-tab-list", core)
        self.assertIn("overflow-x: auto !important", core)
        self.assertIn("flex-wrap: nowrap !important", core)
        self.assertIn("ui-selection-rail--horizontal", order_tabs)
        self.assertIn("ui-order-tab-list", order_tabs)
        self.assertIn("ui-tab-chip ui-selection-control", order_tabs)

    def test_delete_triggers_share_one_destructive_action_contract(self) -> None:
        buttons = source(CSS_DIR / "components" / "buttons.css")
        trigger_templates = (
            "portal/staff/partials/order_delete_button.html",
            "portal/client/partials/order_project_delete_button.html",
            "portal/client/partials/order_project_item_delete_button.html",
            "portal/client/gang_sheets/partials/delete_button.html",
        )

        for marker in (
            ".ui-destructive-action {",
            "--ui-underline-color: var(--danger)",
            "background: transparent !important",
            "font-family: var(--ui-font-display)",
            ":is(.ui-selection-control, .ui-inline-action, .ui-destructive-action)::after",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, buttons)

        for template_path in trigger_templates:
            with self.subTest(template_path=template_path):
                template = source(TEMPLATES_DIR / template_path)
                self.assertIn("ui-destructive-action", template)
                self.assertIn("ui-btn ui-btn-danger", template)
