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
        self.assertNotIn("gradient(", polish)

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
        self.assertIn("ui-form-stack", login)
        self.assertIn("ui-input", login)
        self.assertNotIn("dui-input", login)
        self.assertNotIn("dui-alert", login)

    def test_login_auth_surface_is_a_single_centered_card(self) -> None:
        core = source(CSS_DIR / "entries/portal-core.css")
        login_css = source(CSS_DIR / "components/auth-login.css")
        login = source(TEMPLATES_DIR / "portal/login.html")

        self.assertIn('@import "../components/auth-login.css";', core)
        self.assertLess(core.index('@import "../components/product-polish.css";'), core.index('@import "../components/auth-login.css";'))
        self.assertIn("width: min(100%, 26.5rem)", login_css)
        self.assertIn("grid-template-columns: minmax(0, 1fr)", login_css)
        self.assertNotIn("product-login-heading", login_css)
        self.assertIn("product-login-card__intro", login)
        self.assertEqual(login.count("product-auth-card"), 1)

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
            "outline: 2px solid var(--focus-ring)",
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

    def test_studio_dialog_uses_b2b_kicker_instead_of_hidden_eyebrow(self) -> None:
        editor = source(TEMPLATES_DIR / "portal/client/gang_sheets/editor.html")
        studio_entry = source(CSS_DIR / "entries/studio.css")

        self.assertNotIn("product-eyebrow", editor)
        self.assertIn('class="b2b-dialog-kicker">Fichiers à analyser', editor)
        self.assertIn(".gang-asset-modal-form__controls > .b2b-dialog-kicker", studio_entry)

    def test_marketing_entry_neutralizes_agency_defaults_on_conversion_pages(self) -> None:
        entry = source(CSS_DIR / "entries/marketing.css")

        self.assertIn(
            "body.ui-marketing-body.landing-conversion-page:not(.portal-shell):not(.prospect-tunnel-page)",
            entry,
        )
        self.assertIn("Neutralise les défauts agency-*", entry)
