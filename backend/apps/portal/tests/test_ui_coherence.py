from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
STATIC_SRC_DIR = Path(settings.BASE_DIR) / "static_src"


def template_source(relative_path: str) -> str:
    return (TEMPLATES_DIR / relative_path).read_text(encoding="utf-8")


def static_source(relative_path: str) -> str:
    return (STATIC_SRC_DIR / relative_path).read_text(encoding="utf-8")


def app_source(relative_path: str) -> str:
    return (Path(settings.BASE_DIR) / relative_path).read_text(encoding="utf-8")


class PortalUiCoherenceTests(SimpleTestCase):
    def test_frontend_runtime_dependencies_are_self_hosted(self) -> None:
        source = template_source("base.html")
        legacy_css = static_source("css/legacy/app-legacy.css")
        vendor_script = app_source("scripts/copy-vendor.mjs")

        self.assertIn("img/favicon.svg", source)
        self.assertIn("vendor/htmx-1.9.12.min.js", source)
        self.assertIn("vendor/alpinejs-3.14.3.min.js", source)
        self.assertIn("vendor/fonts/space-grotesk", source)
        self.assertIn("vendor/fonts/dm-sans", source)
        self.assertNotIn("unpkg.com", source)
        self.assertNotIn("fonts.googleapis.com", legacy_css)
        self.assertIn("font-display: swap", legacy_css)
        self.assertIn("@fontsource-variable/dm-sans", vendor_script)
        self.assertIn("@fontsource-variable/space-grotesk", vendor_script)

    def test_every_surface_exposes_a_keyboard_skip_target(self) -> None:
        base = template_source("base.html")
        shell_css = static_source("css/components/shell.css")
        surfaces = [
            "shop/home.html",
            "shop/services.html",
            "prospects/base_tunnel.html",
            "portal/layout.html",
            "portal/login.html",
        ]

        self.assertIn('class="ui-skip-link" href="#main-content"', base)
        self.assertIn(".ui-skip-link:focus-visible", shell_css)
        for path in surfaces:
            with self.subTest(path=path):
                self.assertIn('id="main-content"', template_source(path))

    def test_light_product_surfaces_advertise_light_native_controls(self) -> None:
        for path in ["portal/layout.html", "portal/login.html", "prospects/base_tunnel.html"]:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('<meta name="color-scheme" content="light">', source)
                self.assertNotIn('<meta name="color-scheme" content="dark">', source)

    def test_marketing_runtime_is_lightweight_and_keeps_menu_fallback(self) -> None:
        home = template_source("shop/home.html")
        services = template_source("shop/services.html")
        marketing_script = static_source("js/marketing.js")

        for source in [home, services]:
            self.assertIn("{% block runtime_scripts %}", source)
            self.assertIn("js/marketing.js", source)

        self.assertIn('import "./landing-motion.js', marketing_script)
        self.assertIn('import "./product-shell.js', marketing_script)
        self.assertNotIn("htmx", marketing_script.lower())
        self.assertNotIn("alpine", marketing_script.lower())

    def test_landing_mobile_performance_contract_is_explicit(self) -> None:
        landing_css = static_source("css/components/landing.css")

        self.assertIn("content-visibility: auto", landing_css)
        self.assertIn("contain-intrinsic-block-size: auto 900px", landing_css)
        self.assertIn(".landing-hero__actions", landing_css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", landing_css)
        self.assertIn(".landing-mobile-primary-cta", landing_css)

    def test_product_views_do_not_reintroduce_dark_theme_text_on_light_panels(self) -> None:
        paths = [
            "portal/client/checkout.html",
            "portal/client/partials/checkout_uploads.html",
            "portal/client/partials/checkout_summary.html",
            "portal/client/panels/billing.html",
            "portal/staff/panels/drive_sync.html",
            "prospects/step1.html",
        ]
        forbidden = [
            "text-[#faf7f2]",
            "text-[#f4f0e8]",
            "text-[#f0d4c4]",
            "bg-black/",
            "border-white/",
        ]

        for path in paths:
            source = template_source(path)
            for marker in forbidden:
                with self.subTest(path=path, marker=marker):
                    self.assertNotIn(marker, source)

    def test_checkout_and_prospect_mobile_layouts_are_compact(self) -> None:
        product_css = static_source("css/components/product-shell.css")
        prospect_css = static_source("css/components/prospect-tunnel.css")
        step4 = template_source("prospects/step4.html")

        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", product_css)
        self.assertIn(".product-checkout-card > .dui-card-body", product_css)
        self.assertIn(".product-checkout-submit", product_css)
        self.assertIn("body.prospect-tunnel-page .prospect-shell__trust", prospect_css)
        self.assertIn(
            "body.ui-marketing-body.prospect-tunnel-page .agency-menu-toggle",
            prospect_css,
        )
        self.assertIn("display: none", prospect_css)
        self.assertIn('autocomplete="username"', step4)

    def test_portal_breadcrumb_partials_use_semantic_nav(self) -> None:
        paths = [
            "components/portal/breadcrumbs/client_order_detail.html",
            "components/portal/breadcrumbs/staff_order_detail.html",
            "components/portal/breadcrumbs/checkout_client.html",
            "components/portal/breadcrumbs/client_orders_list.html",
            "components/portal/breadcrumbs/staff_orders_list.html",
        ]

        for path in paths:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('<nav class="ui-breadcrumb"', source)
                self.assertIn('aria-label="Fil d’Ariane"', source)
                self.assertIn('aria-current="page"', source)
                self.assertNotIn('<p class="breadcrumb"', source)

    def test_legacy_glass_surfaces_are_removed_from_audited_templates(self) -> None:
        paths = [
            "portal/login.html",
            "portal/client/checkout.html",
            "portal/client/partials/checkout_uploads.html",
            "portal/client/partials/checkout_summary.html",
            "portal/client/panels/uploads.html",
            "portal/staff/panels/uploads.html",
            "portal/client/panels/billing.html",
            "portal/staff/panels/billing.html",
        ]
        legacy_markers = [
            "landing-auth-shell",
            "ui-form-card",
            "portal-login-card",
            "shadow-xl",
            "backdrop-blur-sm",
            "bg-white/5",
            'role="feed"',
        ]

        for path in paths:
            source = template_source(path)
            for marker in legacy_markers:
                with self.subTest(path=path, marker=marker):
                    self.assertNotIn(marker, source)

    def test_order_tabs_have_keyboard_accessibility_contract(self) -> None:
        source = template_source("components/order/order_tabs.html")
        runtime = static_source("js/htmx/swap-state.js")

        self.assertIn('<h2 class="workflow-shell__title', source)
        self.assertNotIn('<h3 class="workflow-shell__title', source)
        self.assertIn('role="tablist"', source)
        self.assertIn('role="tab"', source)
        self.assertIn('role="tabpanel"', source)
        self.assertIn('aria-controls="{{ panel_id }}"', source)
        self.assertIn('aria-labelledby="{% if active_tab_id %}{{ active_tab_id }}', source)
        self.assertIn('aria-live="polite"', source)
        self.assertIn("aria-busy=", source)
        self.assertIn('data-panel-slug="{{ tab.slug }}"', source)
        self.assertIn('hx-push-url="{{ tab.push_url }}"', source)
        self.assertNotIn("<script>", source)
        self.assertIn("event.detail?.target", runtime)
        self.assertIn("target instanceof HTMLElement", runtime)

    def test_deep_product_views_keep_sequential_heading_levels(self) -> None:
        checkout = template_source("portal/client/checkout.html")
        staff_snapshot = template_source("components/portal/staff_customer_snapshot.html")

        for title in ["Étape 1 — Décrire votre besoin", "Ajout des fichiers", "Résumé"]:
            with self.subTest(title=title):
                self.assertIn(f">{title}</h2>", checkout)
                self.assertNotIn(f">{title}</h3>", checkout)

        self.assertIn(
            '<h2 id="staff-customer-snapshot-heading"',
            staff_snapshot,
        )

    def test_public_mobile_menu_has_non_alpine_fallback_hook(self) -> None:
        source = template_source("components/nav/landing_header.html")

        self.assertIn("data-product-menu-toggle", source)
        self.assertIn("data-product-menu", source)
        self.assertIn('aria-controls="landing-primary-nav"', source)
        self.assertIn('data-menu-open-label="Ouvrir le menu"', source)
        self.assertNotIn("data-landing-menu", source)
        self.assertNotIn("data-landing-menu-toggle", source)
        self.assertNotIn("btn-nav-cta", source)
        self.assertNotIn('class="btn', source)
        self.assertNotIn("x-data", source)
        self.assertNotIn("@click", source)

    def test_public_header_keeps_conversion_navigation_focused(self) -> None:
        source = template_source("components/nav/landing_header.html")

        self.assertIn("Services", source)
        self.assertIn("Cas", source)
        self.assertIn("Contact", source)
        self.assertIn("Connexion", source)
        self.assertIn("Demander un accès", source)
        self.assertNotIn(">Équipe<", source)
        self.assertNotIn(">Commander<", source)
        self.assertNotIn(">Espace client<", source)

    def test_public_header_removes_primary_cta_inside_prospect_tunnel(self) -> None:
        source = template_source("components/nav/landing_header.html")

        self.assertIn('current_namespace != "prospects"', source)
        self.assertIn("Demander un accès", source)

    def test_portal_header_uses_role_focused_labels(self) -> None:
        source = template_source("components/nav/portal_header.html")

        self.assertIn(">Accueil</a>", source)
        self.assertIn(">Nouvelle commande</a>", source)
        self.assertIn(">Tableau de bord</a>", source)
        self.assertIn(">Commandes</a>", source)
        self.assertIn("Navigation", source)
        self.assertIn("Pilotage staff", source)
        self.assertNotIn("Accès sécurisé", source)
        self.assertIn("ui-btn ui-btn-ghost ui-btn-sm shrink-0 product-menu-button", source)
        self.assertIn("product-nav__logout", source)
        self.assertIn("ui-btn ui-btn-primary ui-btn-sm product-nav__login", source)
        self.assertNotIn("Accueil client", source)
        self.assertNotIn("Accueil staff", source)
        self.assertNotIn("Commandes staff", source)
        self.assertNotIn(">Dashboard</a>", source)
        self.assertNotIn("Ops staff", source)
        self.assertNotIn("Backoffice staff", source)
        self.assertNotIn("btn-nav-cta", source)
        self.assertNotIn('class="btn', source)
        self.assertNotIn(">Commander</a>", source)
        self.assertNotIn("x-data", source)
        self.assertNotIn("@click", source)

    def test_auth_login_uses_dedicated_minimal_header(self) -> None:
        source = template_source("portal/login.html")
        header = template_source("components/nav/auth_header.html")

        self.assertIn('include "components/nav/auth_header.html"', source)
        self.assertIn('include "components/brand/logo.html"', header)
        self.assertIn("Retour au site", header)
        self.assertNotIn("data-product-menu-toggle", header)

    def test_all_headers_use_the_same_brand_lockup(self) -> None:
        logo = template_source("components/brand/logo.html")
        legacy_css = static_source("css/legacy/app-legacy.css")
        headers = [
            template_source("components/nav/landing_header.html"),
            template_source("components/nav/portal_header.html"),
            template_source("components/nav/auth_header.html"),
        ]

        self.assertIn("ui-brand-lockup__mark", logo)
        self.assertIn("Prenium DTF", logo)
        self.assertIn("via IDS supply", logo)
        self.assertIn("body .ui-brand-lockup__name", legacy_css)
        self.assertIn("body .ui-brand-lockup__subtitle", legacy_css)
        for header in headers:
            self.assertIn('include "components/brand/logo.html"', header)

    def test_login_hides_internal_roles_and_keeps_only_useful_copy(self) -> None:
        source = template_source("portal/login.html")

        self.assertIn("Retrouvez vos commandes, vos fichiers et vos documents", source)
        self.assertIn("Demander un accès professionnel", source)
        for forbidden in ["client", "staff", "backend", "permissions", "droits"]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())

    def test_staff_dashboard_uses_french_premium_copy(self) -> None:
        source = template_source("portal/staff/dashboard.html")

        self.assertIn('kicker="Pilotage staff"', source)
        self.assertNotIn("Backoffice staff", source)

    def test_saas_button_system_is_imported_with_interaction_tokens(self) -> None:
        input_css = static_source("css/input.css")
        tokens_css = static_source("css/tokens.css")
        buttons_css = static_source("css/components/buttons.css")

        self.assertIn('@import "./components/buttons.css";', input_css)
        self.assertIn("--ui-action-min-h", tokens_css)
        self.assertIn(".ui-btn-primary", buttons_css)
        self.assertIn(".ui-btn-secondary", buttons_css)
        self.assertIn(".ui-btn-danger", buttons_css)
        self.assertIn(":focus-visible", buttons_css)
        self.assertIn("min-height: var(--ui-action-min-h)", buttons_css)

    def test_saas_views_use_semantic_ui_buttons_for_product_actions(self) -> None:
        paths = [
            "portal/login.html",
            "portal/client/checkout.html",
            "portal/client/partials/checkout_uploads.html",
            "portal/client/partials/checkout_summary.html",
            "portal/client/dashboard.html",
            "portal/staff/dashboard.html",
            "portal/staff/order_detail.html",
            "components/portal/staff_meterage_section.html",
            "components/ui/empty_state.html",
            "prospects/step1.html",
            "prospects/step2.html",
            "prospects/step3.html",
            "prospects/step4.html",
            "prospects/confirmation.html",
        ]

        for path in paths:
            source = template_source(path)
            with self.subTest(path=path):
                self.assertIn("ui-btn", source)
                self.assertNotIn('class="btn', source)
                self.assertNotIn('primary_class_full="dui-btn', source)

    def test_order_tabs_persist_panel_state_in_url(self) -> None:
        source = app_source("apps/portal/templatetags/order_tags.py")

        self.assertIn('query["panel"] = slug', source)
        self.assertIn('"push_url"', source)
        self.assertIn('"active_tab_id"', source)
        self.assertIn('"slug": "uploads"', source)
        self.assertIn('"slug": "billing"', source)

    def test_empty_order_states_are_actionable(self) -> None:
        client_source = template_source("portal/client/orders_list.html")
        staff_source = template_source("portal/staff/orders_list.html")

        self.assertIn("Créer une commande", client_source)
        self.assertIn("portal:client-checkout", client_source)
        self.assertIn("Retour au tableau de bord", staff_source)
        self.assertIn("portal:staff-dashboard", staff_source)
        self.assertIn("Aucune commande à afficher.", staff_source)
        self.assertNotIn("Aucune commande a afficher.", staff_source)

    def test_staff_shipping_form_matches_backend_payload_fields(self) -> None:
        source = template_source("portal/staff/panels/shipping.html")

        for field_name in [
            "recipient_company_name",
            "recipient_address_line_2",
            "recipient_phone_number",
        ]:
            with self.subTest(field_name=field_name):
                self.assertIn(f'name="{field_name}"', source)

    def test_staff_layout_removes_redundant_inline_structure_styles(self) -> None:
        staff_detail = template_source("portal/staff/order_detail.html")
        staff_customer = template_source("components/portal/staff_customer_snapshot.html")
        production = template_source("portal/staff/panels/production.html")
        scan = template_source("portal/staff/panels/scan.html")

        self.assertNotIn('class="card order-command-bar" style=', staff_detail)
        self.assertNotIn('class="card staff-customer-snapshot" style=', staff_customer)
        self.assertNotIn('class="workflow-kpi" style=', production)
        self.assertIn('class="workflow-kpi mb-4"', production)
        self.assertIn("workflow-kpi__label--inline", scan)
        self.assertNotIn("display: inline; margin-right", scan)

    def test_prospect_primary_actions_declare_button_hierarchy(self) -> None:
        paths = [
            "prospects/step1.html",
            "prospects/step2.html",
            "prospects/step3.html",
            "prospects/step4.html",
        ]

        for path in paths:
            source = template_source(path)
            with self.subTest(path=path):
                self.assertIn(
                    "ui-btn ui-btn-primary ui-btn-wide prospect-form__btn-primary",
                    source,
                )
                self.assertIn("ui-btn ui-btn-secondary prospect-form__btn-secondary", source)

    def test_prospect_step1_uses_visible_labels_for_text_fields(self) -> None:
        source = template_source("prospects/step1.html")

        for field_id in [
            "id_first_name",
            "id_last_name",
            "id_email",
            "id_phone",
            "id_company",
            "id_country",
        ]:
            with self.subTest(field_id=field_id):
                self.assertIn(f'class="product-form-label" for="{field_id}"', source)
                self.assertNotIn(f'class="ui-sr-only" for="{field_id}"', source)
