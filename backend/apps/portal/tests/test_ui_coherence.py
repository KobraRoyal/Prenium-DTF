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
                self.assertIn('class="ui-breadcrumb"', source)
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
        self.assertIn("Menu", source)
        self.assertIn("Pilotage atelier", source)
        self.assertNotIn("Pilotage staff", source)
        self.assertNotIn("Accès sécurisé", source)
        self.assertIn("ui-btn ui-btn-ghost ui-btn-sm shrink-0 product-menu-button", source)
        self.assertIn("product-nav__link", source)
        self.assertIn("product-nav__cta", source)
        self.assertIn("product-nav__logout", source)
        self.assertIn("product-nav__brand", source)
        self.assertIn("product-nav__primary", source)
        self.assertIn("product-nav__account", source)
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

    def test_portal_header_and_lists_share_the_tablet_breakpoint(self) -> None:
        header = template_source("components/nav/portal_header.html")
        orders = template_source("components/tables/orders_table.html")
        projects = template_source("portal/client/order_projects_list.html")
        product_css = static_source("css/components/product-shell.css")

        self.assertNotIn("md:!hidden", header)
        self.assertNotIn("md:flex", header)
        self.assertIn("@media (max-width: 959px)", product_css)
        self.assertIn(".ui-orders-table-desktop", product_css)
        self.assertIn(".ui-orders-list-mobile", product_css)
        self.assertIn("body.product-shell .ui-data-table thead th", product_css)
        self.assertIn("top: 0", product_css)
        self.assertIn("ui-orders-table-desktop", orders)
        self.assertIn("ui-orders-list-mobile", orders)
        self.assertIn("ui_order_projects_table", projects)
        projects_table = template_source("components/tables/order_projects_table.html")
        self.assertIn("ui-orders-table-desktop", projects_table)
        self.assertIn("ui-orders-list-mobile", projects_table)

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
        self.assertIn("brand_home_url as resolved_brand_home_url", logo)
        self.assertIn("brand_home_href", template_source("components/nav/portal_header.html"))
        self.assertIn("portal:client-dashboard", template_source("components/nav/portal_header.html"))
        self.assertIn("portal:staff-dashboard", template_source("components/nav/portal_header.html"))
        self.assertNotIn("{% url 'home' %}", logo)
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
        client_results = template_source("portal/client/partials/client_orders_list_results.html")
        staff_source = template_source("portal/staff/orders_list.html")

        self.assertIn("Créer une commande", client_results)
        self.assertIn("portal:client-checkout", client_results)
        self.assertIn("client-orders-list-results", client_source)
        self.assertIn('hx-trigger="input changed delay:300ms, search"', client_source)
        self.assertIn("client_orders_list_results.html", client_source)
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

    def test_b2b_order_project_flow_reuses_portal_htmx_contracts(self) -> None:
        detail = template_source("portal/client/order_project_detail.html")
        fields = template_source("portal/client/partials/order_project_fields.html")
        items = template_source("portal/client/partials/order_project_items.html")
        editor = template_source("portal/client/partials/order_project_visual_editor.html")
        add_form = template_source("portal/client/partials/order_project_add_visual_form.html")
        validation_panel = template_source(
            "portal/client/partials/order_project_add_visual_validation_panel.html"
        )
        support_color = template_source(
            "portal/client/partials/order_project_support_color_field.html"
        )
        header = template_source("components/nav/portal_header.html")

        summary = template_source("portal/client/partials/order_project_summary.html")

        self.assertIn('title="Finaliser la commande"', detail)
        self.assertIn("b2b-project-header", detail)
        self.assertIn("ui-breadcrumb__list", summary)
        self.assertIn("b2b-project-toolbar__meta", summary)
        self.assertNotIn('aria-label="Progression du projet"', detail)
        self.assertIn('hx-trigger="change delay:600ms"', fields)
        self.assertIn('hx-indicator="#portal-htmx-indicator"', fields)
        self.assertIn('hx-swap="none"', fields)
        self.assertNotIn("Informations complémentaires", fields)
        self.assertIn("Date souhaitée", fields)
        self.assertNotIn("Mode de commande", fields)
        self.assertNotIn('name="order_mode"', fields)
        self.assertNotIn("Votre référence", fields)
        self.assertNotIn("Référence client final", fields)
        self.assertIn('id="order-project-items"', items)
        self.assertIn('id="order-project-item-dialogs"', items)
        self.assertIn('hx-select-oob="#order-project-summary,#order-project-item-dialogs"', items)
        self.assertIn("client-order-project-item-action", editor)
        self.assertNotIn("Largeur (mm)", editor)
        self.assertIn('type="hidden" name="width_mm"', editor)
        self.assertIn("ui-btn ui-btn-danger", editor)
        validation_dimensions = template_source(
            "portal/client/partials/order_project_validation_dimensions_row.html"
        )
        quality_review = template_source("portal/client/partials/order_project_quality_review.html")
        self.assertIn("order_project_validation_dimensions_row.html", validation_panel)
        self.assertIn("order_project_validation_dimensions_row.html", editor)
        self.assertIn("contour bleu en pointillés", validation_dimensions)
        self.assertIn("Taille", validation_dimensions)
        self.assertIn("limites du fichier", validation_dimensions)
        self.assertNotIn("item.width_mm", quality_review)
        self.assertIn("order_project_item_quantity_field.html", editor)
        self.assertIn('type="hidden" name="width_mm"', add_form)
        self.assertIn("data-configurator-width", add_form)
        self.assertNotIn("Largeur (mm)", add_form)
        self.assertIn("data-analysis-pending", items)
        self.assertIn('hx-trigger="load delay:1400ms"', items)
        self.assertIn("order_project_quality_review.html", items)
        self.assertIn("order_project_preview_stage.html", validation_panel)
        self.assertIn("order_project_rotation_hidden.html", validation_panel)
        self.assertNotIn("Rotation autorisée", validation_panel)
        self.assertNotIn("Rotation autorisée", editor)
        self.assertNotIn("Rotation autorisée", add_form)
        self.assertIn("Aperçu en préparation", items)
        self.assertIn("is-analyzing", items)
        self.assertIn("order_project_analysis_loader.html", items)
        analysis_loader = template_source("portal/client/partials/order_project_analysis_loader.html")
        self.assertIn("b2b-analysis-loader--overlay", analysis_loader)
        self.assertIn("resolution_display", quality_review)
        preview_stage = template_source("portal/client/partials/order_project_preview_stage.html")
        self.assertIn("data-thin-zone-overlay", preview_stage)
        self.assertIn("data-thin-zone-toggle", preview_stage)
        self.assertIn("data-semi-transparency-overlay", preview_stage)
        self.assertIn("data-semi-transparency-toggle", preview_stage)
        self.assertIn("data-preview-zoom-in", preview_stage)
        self.assertIn("data-preview-zoom-out", preview_stage)
        self.assertIn("data-preview-zoom-reset", preview_stage)
        self.assertIn("order_project_analysis_loader.html", preview_stage)
        self.assertIn("is-analyzing", preview_stage)
        self.assertIn("is-analysis-pending", validation_panel)
        self.assertIn("is-analysis-pending", editor)
        self.assertIn("Couleur du support obligatoire", preview_stage)
        self.assertIn("b2b-quality-review--compact", quality_review)
        self.assertNotIn("Dimensions et résolution calculées", items)
        self.assertNotIn("Points à connaître", items)
        self.assertIn('name="confirm_analysis"', editor)
        self.assertIn("semi-transparences", editor)
        self.assertIn("order_project_support_color_field.html", editor)
        self.assertIn("data-support-color-hex", support_color)
        self.assertIn("data-support-color-multicolor", support_color)
        self.assertIn("data-support-color-required", support_color)
        self.assertIn("b2b-support-color__badge", support_color)
        self.assertIn("Détails sous 0,5 mm détectés", support_color)
        self.assertIn("légèrement visible si la couleur du textile", support_color)
        self.assertNotIn("Sans cette couleur", support_color)
        self.assertIn('required aria-required="true"', support_color)
        self.assertIn("b2b-swatch-btn", support_color)
        self.assertIn("b2b-swatch-btn--rainbow", support_color)
        self.assertIn("b2b_hex_color_swatch.html", support_color)
        hex_swatch = template_source("portal/client/partials/b2b_hex_color_swatch.html")
        self.assertIn("b2b-swatch-btn--custom", hex_swatch)
        self.assertIn("Ouvrir", items)
        self.assertIn("Supprimer", items)
        self.assertNotIn("data-awaiting-validation", items)
        self.assertNotIn("Valider ces informations", items)
        self.assertIn("confirm-analysis", editor)
        self.assertIn('data-dialog-open="add-visual-dialog"', items)
        self.assertIn('data-dialog-open="visual-dialog-{{ item.public_id }}"', items)
        self.assertNotIn("Ajouter à ma commande", items)
        configurator_runtime = static_source("js/b2b-configurator.js")
        self.assertIn("image.naturalWidth", configurator_runtime)
        self.assertIn("25.4", configurator_runtime)
        self.assertIn("setPreviewBackground", configurator_runtime)
        self.assertIn("data-thin-zone-toggle", configurator_runtime)
        self.assertIn("data-semi-transparency-toggle", configurator_runtime)
        self.assertIn("scheduleFitPreviewMedia", configurator_runtime)
        self.assertIn("is-preview-fitted", configurator_runtime)
        self.assertIn("applyPreviewZoom", configurator_runtime)
        self.assertIn("data-preview-zoom-in", configurator_runtime)
        self.assertIn("dialog.showModal()", configurator_runtime)
        self.assertIn('file.type === "application/pdf"', configurator_runtime)
        self.assertIn("data-configurator-document-preview", configurator_runtime)
        self.assertIn("pdfJsModuleUrl", configurator_runtime)
        self.assertIn('background: "rgba(0, 0, 0, 0)"', configurator_runtime)
        self.assertIn("findConfiguratorRoot", configurator_runtime)
        self.assertIn("data-support-color-hex", configurator_runtime)
        self.assertIn("data-hex-color-control", configurator_runtime)
        self.assertIn("initHexColorControls", configurator_runtime)
        self.assertIn("readEmbeddedDpiFromFile", configurator_runtime)
        self.assertIn("b2b-swatch-btn--checker", add_form)
        self.assertIn("b2b_hex_color_swatch.html", add_form)
        self.assertIn("b2b-swatch-btn--rainbow-ring", hex_swatch)
        self.assertIn("b2b-swatch-btn--custom", hex_swatch)
        self.assertIn("data-hex-color-native", hex_swatch)
        self.assertIn("mountHexPopover", configurator_runtime)
        self.assertIn("b2b-preview-bounds", add_form)
        self.assertIn("data-configurator-bounds", add_form)
        self.assertIn("setMulticolorMode", configurator_runtime)
        self.assertIn("handleSupportColorFieldEvent", configurator_runtime)
        self.assertIn("htmx:load", configurator_runtime)
        items_response = template_source("portal/client/partials/order_project_items_response.html")
        self.assertIn("add-visual-dialog-body", items_response)
        self.assertIn("active_validation_item", items_response)
        self.assertIn("artboard", configurator_runtime)
        self.assertNotIn("Aperçu généré après validation", configurator_runtime)
        self.assertNotIn("window.location.reload()", configurator_runtime)
        self.assertNotIn("HTMLIFrameElement", configurator_runtime)
        self.assertNotIn("innerHTML", configurator_runtime)
        self.assertNotIn("Configurateur DTF", header)
        self.assertIn("Projets B2B", header)
        dashboard = template_source("portal/client/dashboard.html")
        self.assertNotIn("client-dashboard-toolbar", dashboard)
        self.assertNotIn(">Nouvelle commande</a>", dashboard)
        self.assertIn("Commandes à finaliser", dashboard)
        self.assertIn("Commandes transmises", dashboard)
        self.assertNotIn("Commandes à continuer", dashboard)
        self.assertNotIn("Préparer une commande", dashboard)
        self.assertNotIn("Créer un projet DTF", dashboard)
        self.assertNotIn("Envoyer des fichiers prêts", dashboard)
        self.assertNotIn("Accès isolé", dashboard)
        self.assertNotIn("Suivre les statuts", dashboard)

        start_form = template_source("portal/client/order_project_form.html")
        self.assertNotIn("Mode de commande", start_form)
        self.assertNotIn('name="order_mode"', start_form)
        self.assertIn("Étape 1 sur 2", start_form)
        self.assertIn("Ajouter mes visuels", start_form)
        self.assertIn('name="requested_date"', start_form)
        self.assertIn("components/forms/product_date_field.html", start_form)
        self.assertNotIn('type="date"', start_form)
        date_field = template_source("components/forms/product_date_field.html")
        self.assertIn("data-product-date-picker", date_field)
        self.assertIn("Date souhaitée", start_form)
        self.assertIn('name="customer_comment"', start_form)
