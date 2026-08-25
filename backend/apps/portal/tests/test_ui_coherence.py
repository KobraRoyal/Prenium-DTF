import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"
STATIC_SRC_DIR = Path(settings.BASE_DIR) / "static_src"


def template_source(relative_path: str) -> str:
    return (TEMPLATES_DIR / relative_path).read_text(encoding="utf-8")


def staff_dashboard_markup() -> str:
    return template_source("portal/staff/dashboard.html") + template_source(
        "portal/staff/partials/dashboard_worklist_panel.html"
    )


def static_source(relative_path: str) -> str:
    return (STATIC_SRC_DIR / relative_path).read_text(encoding="utf-8")


def app_source(relative_path: str) -> str:
    return (Path(settings.BASE_DIR) / relative_path).read_text(encoding="utf-8")


class PortalUiCoherenceTests(SimpleTestCase):
    def test_staff_inspection_separates_automatic_analysis_from_atelier_decision(self):
        source = template_source("portal/staff/panels/inspection.html")

        self.assertIn("Analyse automatique", source)
        self.assertIn("Décision Atelier", source)
        self.assertIn("Analyse réussie", source)
        self.assertIn("Approuver pour production", source)
        self.assertIn("Demander une correction au client", source)
        self.assertIn('hx-target="#staff-order-inspection-panel"', source)
        self.assertNotIn("warning / erreur", source)
        self.assertNotIn("|human_status", source)

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

    def test_product_surfaces_inherit_light_native_controls_from_base(self) -> None:
        base = template_source("base.html")
        self.assertIn('<meta name="color-scheme" content="light">', base)
        for path in ["portal/layout.html", "portal/login.html", "prospects/base_tunnel.html"]:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertNotIn('<meta name="color-scheme"', source)

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

        landing_motion = static_source("js/landing-motion.js")
        self.assertIn("initLandingHeaderState", landing_motion)
        self.assertNotIn("initLandingBoardTilt", landing_motion)
        self.assertNotIn('addEventListener("pointermove"', landing_motion)
        self.assertIn("initLandingSmoothAnchors", landing_motion)
        self.assertIn('header.classList.toggle("is-scrolled"', landing_motion)
        self.assertIn("IntersectionObserver", landing_motion)
        self.assertIn("prefers-reduced-motion", landing_motion)

    def test_landing_mobile_performance_contract_is_explicit(self) -> None:
        landing_css = static_source("css/components/landing.css")
        conversion_css = static_source("css/components/landing-conversion.css")
        marketing_entrypoint = static_source("css/entries/marketing.css")

        self.assertIn("content-visibility: auto", landing_css)
        self.assertIn("contain-intrinsic-block-size: auto 900px", landing_css)
        self.assertIn(".landing-hero__actions", landing_css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", landing_css)
        self.assertIn(".landing-mobile-primary-cta", landing_css)
        self.assertIn("content-visibility: auto", conversion_css)
        self.assertIn("contain-intrinsic-block-size: auto 900px", conversion_css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", conversion_css)
        self.assertIn('@import "../components/landing-conversion.css"', marketing_entrypoint)

    def test_marketing_services_page_uses_conversion_shell(self) -> None:
        source = template_source("shop/services.html")
        partials = "".join(
            template_source(path)
            for path in [
                "shop/partials/services_hero.html",
                "shop/partials/services_benefits.html",
                "shop/partials/services_use_cases.html",
                "shop/partials/services_cta_final.html",
            ]
        )

        self.assertIn("landing-conversion-page", source)
        self.assertIn("landing-main", source)
        self.assertIn("js/marketing.js", source)
        self.assertNotIn("agency-section", source)
        self.assertNotIn("agency-button", partials)
        self.assertIn("conversion-button--primary", partials)

    def test_landing_conversion_keeps_one_primary_funnel_and_no_duplicate_form(self) -> None:
        home = template_source("shop/home.html")
        hero = template_source("shop/partials/landing_hero.html")
        process = template_source("shop/partials/landing_how_it_works.html")
        final_cta = template_source("shop/partials/landing_cta_final.html")

        self.assertIn("landing-conversion-page", home)
        self.assertNotIn('include "shop/partials/landing_contact.html"', home)
        self.assertNotIn('include "shop/partials/landing_team.html"', home)
        self.assertIn("prospects:step1", hero)
        self.assertNotIn("prospects:step1", process)
        self.assertNotIn("conversion-button", process)
        self.assertIn("prospects:step1", final_cta)
        self.assertNotIn("<form", hero + process + final_cta)
        self.assertNotIn("{% url 'services' %}", final_cta)

    def test_audit_followups_remove_gated_reveal_side_tab_and_width_motion(self) -> None:
        conversion_css = static_source("css/components/landing-conversion.css")
        tunnel_css = static_source("css/components/prospect-tunnel.css")
        journey_css = static_source("css/components/prospect-journey.css")
        tunnel_base = template_source("prospects/base_tunnel.html")
        design_md = (Path(settings.BASE_DIR).parent / "DESIGN.md").read_text(encoding="utf-8")

        self.assertIn("Contenu toujours lisible", conversion_css)
        self.assertNotIn("filter: blur(5px)", conversion_css)
        self.assertNotIn("border-left: 4px solid var(--success)", tunnel_css)
        self.assertIn("transform: scaleX(calc(var(--progress, 0) / 100))", tunnel_css)
        self.assertIn("transition: transform 280ms", journey_css)
        self.assertIn('style="--progress:', tunnel_base)
        self.assertNotIn('style="width:', tunnel_base)
        self.assertIn("name: Prenium DTF", design_md)
        self.assertIn("## Do's and Don'ts", design_md)

    def test_landing_impeccable_accessibility_and_visual_contracts(self) -> None:
        landing_css = static_source("css/components/landing.css")
        conversion_css = static_source("css/components/landing-conversion.css")
        shell_css = static_source("css/components/shell.css")
        base = template_source("base.html")
        logo = template_source("components/brand/logo.html")
        partials = "".join(
            template_source(path)
            for path in [
                "shop/partials/landing_services.html",
                "shop/partials/landing_quality_proof.html",
                "shop/partials/landing_case_studies.html",
                "shop/partials/landing_how_it_works.html",
                "shop/partials/landing_faq.html",
                "shop/partials/landing_cta_final.html",
            ]
        )

        self.assertIn(":not(.conversion-button)", landing_css)
        self.assertIn(
            "body.landing-conversion-page .conversion-button.conversion-button--primary",
            conversion_css,
        )
        self.assertIn(
            "body.ui-marketing-body.landing-conversion-page .conversion-hero h1",
            conversion_css,
        )
        self.assertIn("font-size: clamp(3.6rem, 6.2vw, 6rem)", conversion_css)
        self.assertIn("letter-spacing: -0.035em", conversion_css)
        self.assertIn("@keyframes conversion-hero-title-in", conversion_css)
        self.assertIn("@keyframes conversion-status-pulse", conversion_css)
        self.assertIn("@keyframes conversion-scroll-progress", conversion_css)
        self.assertIn("animation-timeline: scroll(root block)", conversion_css)
        self.assertIn("prefers-reduced-motion: reduce", conversion_css)
        self.assertIn(
            "body.ui-marketing-body.landing-conversion-page .product-header.is-scrolled",
            shell_css,
        )
        self.assertIn("product-menu-button", template_source("components/nav/landing_header.html"))
        self.assertIn("ui-foundation-nav", template_source("components/nav/landing_header.html"))
        self.assertIn(
            ".conversion-button.conversion-button--ghost:hover",
            conversion_css,
        )
        self.assertIn(
            ".conversion-final .conversion-button--primary:hover",
            conversion_css,
        )
        self.assertIn("-webkit-text-fill-color: var(--conversion-ink) !important", conversion_css)
        self.assertNotIn("7.4rem", conversion_css)
        self.assertNotIn("letter-spacing: -0.055em", conversion_css)
        self.assertNotIn("background-size: 54px 54px", conversion_css)
        self.assertNotIn("background-size: 48px 48px", landing_css)
        self.assertNotIn("conversion-kicker", partials)
        self.assertNotIn("conversion-transform__index", partials)
        self.assertIn("min-height: 2.75rem", conversion_css)
        self.assertIn("{% static 'css/app.css' %}", base)
        self.assertIn("{% static 'js/app.js' %}", base)
        self.assertNotIn("app.css' %}?v=", base)
        self.assertNotIn("app.js' %}?v=", base)
        self.assertIn("ui-brand-lockup__home", logo)
        self.assertIn("Contenu toujours lisible", conversion_css)
        self.assertIn("transform: translate3d(0, 1.1rem, 0)", conversion_css)
        self.assertNotIn("filter: blur(5px)", conversion_css)
        self.assertIn("@keyframes conversion-accent-draw", conversion_css)
        self.assertIn("@keyframes conversion-board-step-in", conversion_css)
        self.assertIn("@keyframes conversion-em-underline", conversion_css)
        self.assertIn("scroll-behavior: smooth", conversion_css)
        self.assertIn(
            'include "shop/partials/landing_footer.html"', template_source("shop/home.html")
        )
        self.assertIn("conversion-footer", template_source("shop/partials/landing_footer.html"))
        self.assertIn('role="contentinfo"', template_source("shop/partials/landing_footer.html"))
        self.assertEqual(logo.count("<a "), 1)

    def test_client_order_detail_polish_keeps_one_surface_and_mobile_contracts(self) -> None:
        detail = template_source("portal/client/order_detail.html")
        breadcrumb = template_source("components/portal/breadcrumbs/client_order_detail.html")
        product_css = static_source("css/components/product-shell.css")
        panels = "".join(
            template_source(path)
            for path in [
                "portal/client/panels/uploads.html",
                "portal/client/panels/production.html",
                "portal/client/panels/shipping.html",
                "portal/client/panels/billing.html",
                "portal/client/panels/inspection.html",
            ]
        )

        self.assertIn("client-order-detail", detail)
        self.assertIn("portal-page--client", detail)
        self.assertIn("components/portal/page_head.html", detail)
        self.assertIn("page_head_leads/client_order_detail.html", detail)
        self.assertIn('class="client-order-summary__facts"', detail)
        self.assertIn("Commande soumise", detail)
        self.assertIn("Tarification", detail)
        self.assertIn("Informations transmises", detail)
        self.assertIn("order_client_label|default:order_short_ref", detail)
        self.assertNotIn('subtitle_prefix="Votre référence"', detail)
        self.assertNotIn("page-head__eyebrow", detail)
        self.assertIn("client-order-panel", panels)
        self.assertNotIn('class="panel client-order-panel', panels)
        self.assertNotIn('article class="card"', panels)
        self.assertIn("ui_kpi_grid", panels)
        self.assertIn("client-billing-overview", panels)
        self.assertIn("client-billing-pay", panels)
        self.assertIn("client-billing-success", panels)
        self.assertIn("client-shipment-card", panels)
        self.assertIn("Votre commande est en route", panels)
        self.assertIn("Suivre mon colis", panels)
        self.assertIn("Merci, c’est confirmé", panels)
        self.assertIn("pay-order-dialog-", panels)
        self.assertIn("Télécharger le justificatif", panels)
        self.assertIn("b2b-settlement-choice__option", panels)
        self.assertIn("Payer maintenant", panels)
        self.assertIn("Paiement non finalisé", panels)
        self.assertNotIn("Relancer le paiement", panels)
        self.assertNotIn("Reprendre le paiement en cours", panels)
        self.assertIn("Continuer vers le paiement", panels)
        self.assertIn("order_status_banner", detail)
        self.assertIn("client-order-detail-banner", detail)
        self.assertIn(
            'class="ui-btn ui-btn-primary ui-btn-sm" href="?panel=billing&amp;pay=1"',
            detail,
        )
        self.assertNotIn('class="link font-medium"', detail)
        self.assertEqual(detail.count('role="status"'), 1)
        self.assertIn("client-order-list", breadcrumb)
        self.assertNotIn("ui-breadcrumb__item--order-ref", breadcrumb)
        self.assertNotIn("Accueil client", breadcrumb)
        self.assertIn(".client-order-detail .workflow-panel", product_css)
        self.assertIn("box-shadow: none !important", product_css)
        self.assertIn("min-height: 2.75rem", product_css)
        self.assertIn("overflow-x: auto", product_css)

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

    def test_product_shell_reduced_motion_and_critical_microcopy_contracts(self) -> None:
        product_css = static_source("css/components/product-shell.css")

        self.assertIn("--product-text-critical-xs: 0.75rem", product_css)
        self.assertIn("html:has(body.product-shell)", product_css)
        self.assertIn("body.product-shell .product-layout > *", product_css)
        self.assertIn("body.product-shell .b2b-preview-stage.is-analyzing", product_css)
        self.assertIn("animation: none !important", product_css)
        self.assertIn("scroll-behavior: auto !important", product_css)
        self.assertNotIn("animation-duration: 0.01ms", product_css)
        self.assertNotIn("transition-duration: 0.01ms", product_css)
        self.assertNotIn("body.product-shell *::before", product_css)

        workflow_block = product_css.split("body.product-shell .workflow-next-action {", 1)[
            1
        ].split("}", 1)[0]
        self.assertNotIn("border-left", workflow_block)
        self.assertIn("border: 2px solid var(--product-line)", workflow_block)
        self.assertIn("body.product-shell .workflow-next-action::before", product_css)

        critical_selectors = [
            ".product-profile__action small",
            ".account-team-status",
            ".workflow-next-action__label",
            ".product-date-picker__weekdays",
            ".b2b-support-color__required-hint",
            ".atelier-order-row__select-hint",
            ".client-billing-pay__amount span",
            ".client-shipment-card__fact dt",
        ]
        for selector in critical_selectors:
            with self.subTest(selector=selector):
                self.assertRegex(
                    product_css,
                    re.escape(selector)
                    + r"[^{}]*\{[^}]*font-size: var\(--product-text-critical-xs\)",
                )

    def test_branding_settings_use_portal_alert_contract(self) -> None:
        branding = template_source("portal/staff/settings/branding.html")

        self.assertIn("alert alert--danger", branding)
        self.assertIn("alert alert--info", branding)
        self.assertNotIn("ui-alert", branding)

    def test_checkout_and_prospect_mobile_layouts_are_compact(self) -> None:
        product_css = static_source("css/components/product-shell.css")
        prospect_css = static_source("css/components/prospect-tunnel.css")
        journey_css = static_source("css/components/prospect-journey.css")
        invitation = template_source("portal/access/invitation_accept.html")

        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr))", product_css)
        self.assertIn(".product-checkout-card > .dui-card-body", product_css)
        self.assertIn(".product-checkout-submit", product_css)
        self.assertIn("body.prospect-tunnel-page .prospect-shell__trust", prospect_css)
        self.assertIn(
            "body.ui-marketing-body.prospect-tunnel-page .agency-menu-toggle",
            prospect_css,
        )
        self.assertIn("display: none", prospect_css)
        self.assertIn("@media (max-width: 767px)", journey_css)
        self.assertIn("grid-template-columns: 1fr", journey_css)
        self.assertIn("prefers-reduced-motion: reduce", journey_css)
        self.assertIn('autocomplete="new-password"', invitation)

    def test_portal_breadcrumb_partials_use_semantic_nav(self) -> None:
        canonical_trails = [
            "components/portal/breadcrumbs/staff_trail.html",
            "components/portal/breadcrumbs/client_trail.html",
        ]
        trail_wrappers = [
            "components/portal/breadcrumbs/client_dashboard.html",
            "components/portal/breadcrumbs/client_orders_list.html",
            "components/portal/breadcrumbs/client_gang_sheets_list.html",
            "components/portal/breadcrumbs/staff_orders_list.html",
            "components/portal/breadcrumbs/staff_customers_list.html",
        ]
        bespoke_paths = [
            "components/portal/breadcrumbs/client_order_detail.html",
            "components/portal/breadcrumbs/client_order_project_detail.html",
            "components/portal/breadcrumbs/client_gang_sheet_editor.html",
            "components/portal/breadcrumbs/client_order_project_form.html",
            "components/portal/breadcrumbs/client_gang_sheet_create_order.html",
            "components/portal/breadcrumbs/staff_order_detail.html",
            "components/portal/breadcrumbs/checkout_client.html",
        ]

        for path in canonical_trails:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('class="ui-breadcrumb"', source)
                self.assertIn('aria-label="Fil d’Ariane"', source)
                self.assertIn('aria-current="page"', source)
                self.assertNotIn('<p class="breadcrumb"', source)

        for path in trail_wrappers:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn("_trail.html", source)

        for path in bespoke_paths:
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

        self.assertNotIn("workflow-shell__head", source)
        self.assertIn('role="tablist"', source)
        self.assertIn('role="tab"', source)
        self.assertIn('role="tabpanel"', source)
        self.assertIn('aria-controls="{{ panel_id }}"', source)
        self.assertIn('{% if active_tab_id %}aria-labelledby="{{ active_tab_id }}"', source)
        self.assertIn('aria-live="polite"', source)
        self.assertIn("aria-busy=", source)
        self.assertIn('data-panel-slug="{{ tab.slug }}"', source)
        self.assertIn('hx-push-url="{{ tab.push_url }}"', source)
        self.assertNotIn("tab_icon.html", source)
        self.assertNotIn("<svg", source)
        self.assertNotIn("<script>", source)
        self.assertIn("event.detail?.target", runtime)
        self.assertIn("target instanceof HTMLElement", runtime)

    def test_scan_is_replaced_by_the_dedicated_operations_console(self) -> None:
        tabs = app_source("apps/portal/templatetags/order_tags.py")
        operations = template_source("portal/staff/operations/index.html")
        workspace = template_source("portal/staff/operations/_workspace.html")
        focus_card = template_source("portal/staff/operations/_focus_card.html")
        operator_workflow = template_source("portal/staff/operations/_operator_workflow.html")
        operator_meterage = template_source("portal/staff/operations/_operator_meterage.html")
        row = template_source("portal/staff/operations/_job_row.html")
        shipping_form = template_source("portal/staff/operations/_shipping_form.html")
        portal_css = static_source("css/entries/portal-staff.css")

        self.assertNotIn('"slug": "scan"', tabs)
        self.assertNotIn("Scan atelier", tabs)
        self.assertIn("Pilotage Atelier", operations)
        self.assertIn("operationScan.focus", operations)
        self.assertIn("atelier-operations-scan-bar", operations)
        self.assertIn("Scanner un OF", operations)
        self.assertIn("Afficher la commande", operations)
        self.assertNotIn("ui-list-command--stats-only", operations)
        self.assertNotIn("next_focus_row", operations)
        self.assertNotIn("atelier-operations-next-action", operations)
        self.assertIn('id="atelier-operations-panel"', workspace)
        self.assertIn("En attente de scan", workspace)
        self.assertIn("focus_row", workspace)
        self.assertIn("ui_list_tabs", focus_card)
        self.assertIn("atelier-operations-focus__tabs", focus_card)
        self.assertIn("atelier-operations-focus", focus_card)
        self.assertIn("Commande identifiée", focus_card)
        self.assertIn("_operator_workflow.html", focus_card)
        self.assertIn("atelier-operator-workflow", operator_workflow)
        self.assertIn("atelier-stepper", operator_workflow)
        self.assertIn("atelier-stepper__track", operator_workflow)
        self.assertIn("atelier-stepper__marker", operator_workflow)
        self.assertIn("Parcours de production", operator_workflow)
        self.assertNotIn("workflow-progress", operator_workflow)
        self.assertNotIn("ui-tab-chip", operator_workflow)
        self.assertNotIn("atelier-operator-steps", operator_workflow)
        self.assertIn("staff-atelier-operation-upload-review", operator_workflow)
        self.assertIn("staff-atelier-operation-machine-assign", operator_workflow)
        self.assertIn("staff-atelier-operation-print-confirm", operator_workflow)
        self.assertIn("require_machine_selection", operator_workflow)
        self.assertLess(
            operator_workflow.index("atelier-operator-panel--control"),
            operator_workflow.index("atelier-operator-panel--machine"),
        )
        self.assertLess(
            operator_workflow.index("atelier-operator-panel--machine"),
            operator_workflow.index("_operator_meterage.html"),
        )
        self.assertLess(
            operator_workflow.index("_operator_meterage.html"),
            operator_workflow.index("atelier-operator-panel--print"),
        )
        self.assertLess(
            operator_workflow.index("atelier-operator-panel--print"),
            operator_workflow.index("atelier-operator-panel--shipping"),
        )
        self.assertIn("staff-atelier-operation-meterage", operator_meterage)
        self.assertNotIn("atelier-operations-list", workspace)
        self.assertNotIn("atelier-operations-tab", workspace)
        self.assertIn("staff-atelier-operation-transition", row)
        self.assertIn("staff-atelier-operation-shipment-create", shipping_form)
        self.assertIn("atelier-operations.css", portal_css)

    def test_staff_order_detail_keeps_only_actionable_summary(self) -> None:
        source = template_source("portal/staff/order_detail.html")
        delete_partial = template_source("portal/staff/partials/order_delete_button.html")
        breadcrumb = template_source("components/portal/breadcrumbs/staff_order_detail.html")

        self.assertIn("staff-order-detail-identity", source)
        self.assertIn("staff-order-focus__header", source)
        self.assertIn("atelier-next-action", source)
        self.assertIn("Prochain geste", source)
        self.assertIn("staff-order-focus__of", source)
        self.assertIn("staff-order-focus__client", source)
        self.assertIn("order.total_amount", source)
        self.assertIn("Dossier Drive", source)
        self.assertNotIn("staff-order-focus__facts", source)
        self.assertNotIn("Créée le", source)
        self.assertNotIn("Retour à la file", source)
        self.assertNotIn("Ordre de fabrication", source)
        self.assertNotIn("Référence", source)
        self.assertIn("order_payment_captured", source)
        self.assertIn("À encaisser", source)
        self.assertNotIn("Payée", source)
        self.assertNotIn("settlement_badge", source)
        self.assertNotIn("Mode de facturation", source)
        self.assertIn("portal/staff/partials/order_delete_button.html", source)
        self.assertIn("{% if can_delete_order %}", source)
        self.assertIn("portal:staff-order-delete", delete_partial)
        self.assertIn("can_delete_order", delete_partial)
        self.assertIn("staff_order_focus.order_reference", breadcrumb)
        self.assertNotIn("staff_customer_snapshot.html", source)
        self.assertNotIn("staff_order_workflow_summary.html", source)
        self.assertNotIn("order-command-bar", source)
        self.assertNotIn("▸", source)
        self.assertNotIn("<svg", source)

    def test_staff_orders_table_shows_settlement_badge(self) -> None:
        orders = template_source("components/tables/orders_table.html")
        billing = template_source("portal/staff/panels/billing.html")

        self.assertIn("settlement_badge", orders)
        self.assertIn('variant == "staff"', orders)
        self.assertIn("settlement_badge", billing)
        self.assertNotIn("settlement_badge", template_source("portal/staff/panels/production.html"))

    def test_staff_customer_detail_exposes_settlement_mode_choice(self) -> None:
        source = template_source("portal/staff/customers/detail.html")
        listing = template_source("portal/staff/customers/list.html")
        statements = template_source("portal/staff/customers/_billing_statements.html")

        self.assertIn("staff-customer-focus", source)
        self.assertIn("staff-customer-detail-identity", source)
        self.assertIn("staff-customer-workspace", source)
        self.assertLess(
            source.index("staff-customer-detail-identity"),
            source.index("data-customer-workspace"),
        )
        self.assertIn("default_billing_mode", source)
        self.assertIn("b2b-settlement-choice__option", source)
        self.assertIn("Comptant — carte bancaire", source)
        self.assertIn("settlement_badge", listing)
        self.assertIn("default_billing_mode", listing)
        self.assertIn("customer-billing-statements", statements)
        self.assertIn("staff-customer-billing-statement-create", statements)
        self.assertIn("staff-customer-billing-statement-export", statements)
        self.assertNotIn("Facturation externalisée", statements)

    def test_staff_customer_detail_distills_long_account_into_accessible_workspace(self) -> None:
        source = template_source("portal/staff/customers/detail.html")
        statements = template_source("portal/staff/customers/_billing_statements.html")
        workspace_css = static_source("css/components/customer-account-workspace.css")
        portal_entrypoint = static_source("css/entries/portal-staff.css")
        runtime = static_source("js/customer-account-workspace.js")

        self.assertIn("data-customer-workspace", source)
        for section_id in [
            "customer-account",
            "customer-pricing",
            "customer-volume",
            "billing-statements",
            "customer-access",
        ]:
            with self.subTest(section_id=section_id):
                combined_templates = f"{source}\n{statements}"
                self.assertIn(f'id="{section_id}"', combined_templates)
                self.assertIn(f'href="#{section_id}"', source)

        self.assertIn("<details", source)
        self.assertIn("staff-customer-subsection", source)
        self.assertIn("staff-customer-subsection__copy", source)
        self.assertIn("staff-customer-address__locality", source)
        self.assertIn('field_class="staff-customer-address__country"', source)
        self.assertIn("staff-customer-form__actions", source)
        self.assertNotIn("sm:grid-cols-3", source)
        self.assertIn("account_address_has_errors", source)
        self.assertIn("volume_discount_has_errors", source)
        self.assertIn("data-customer-section", statements)
        self.assertIn("position: sticky", workspace_css)
        self.assertIn("grid-template-columns: minmax(7.5rem, 0.8fr)", workspace_css)
        self.assertIn(".staff-customer-settlement", workspace_css)
        self.assertIn(
            'staff-customer-settlement .b2b-settlement-choice__option input[type="radio"]',
            portal_entrypoint,
        )
        self.assertIn("@media (max-width: 639px)", workspace_css)
        self.assertIn("customer-account-workspace.css", portal_entrypoint)
        self.assertIn("revealCustomerSection", runtime)
        self.assertIn("prefers-reduced-motion: reduce", runtime)
        self.assertIn("js/customer-account-workspace.js", source)

    def test_staff_access_requests_match_staff_entity_patterns(self) -> None:
        listing = template_source("portal/staff/access_requests/list.html")
        detail = template_source("portal/staff/access_requests/detail.html")
        list_crumb = template_source(
            "components/portal/breadcrumbs/staff_access_requests_list.html"
        )
        detail_crumb = template_source(
            "components/portal/breadcrumbs/staff_access_request_detail.html"
        )

        self.assertIn(
            "components/portal/breadcrumbs/staff_access_requests_list.html",
            listing,
        )
        self.assertIn("staff-data-list", listing)
        self.assertIn("profile.status|badge_tone", listing)
        self.assertIn("ui_list_tabs", listing)
        self.assertIn("access-request-command", listing)
        self.assertIn("ui-list-command", listing)
        self.assertIn("access-request-search", listing)
        self.assertIn("profile.get_monthly_volume_display", listing)
        self.assertIn("profile.get_urgency_display", listing)
        self.assertIn("aria-current", template_source("components/ui/list_tabs.html"))

        self.assertIn("staff-access-focus", detail)
        self.assertIn("staff-access-panel", detail)
        self.assertIn("approval_form.review_note", detail)
        self.assertIn("rejection_form.rejection_reason", detail)
        self.assertIn("Valider et envoyer l’activation", detail)
        self.assertIn("Refuser et notifier", detail)
        self.assertIn("workflow-panel__feedback", detail)
        self.assertIn("portal:staff-access-request-list", detail_crumb)
        self.assertIn("Demandes d’accès", list_crumb)
        self.assertNotIn("dui-alert", detail)

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
        self.assertIn("product-menu-button", source)
        self.assertIn("ui-foundation-nav", source)
        self.assertIn('data-menu-open-label="Ouvrir le menu"', source)
        self.assertNotIn("data-landing-menu", source)
        self.assertNotIn("data-landing-menu-toggle", source)
        self.assertNotIn("btn-nav-cta", source)
        self.assertNotIn('class="btn', source)
        self.assertNotIn("x-data", source)
        self.assertNotIn("@click", source)

    def test_public_header_keeps_conversion_navigation_focused(self) -> None:
        source = template_source("components/nav/landing_header.html")

        self.assertIn("Solutions", source)
        self.assertIn("Méthode", source)
        self.assertIn("Pour qui", source)
        self.assertIn("Connexion", source)
        self.assertIn("Demander un accès", source)
        self.assertNotIn("Contact", source)
        self.assertNotIn(">Équipe<", source)
        self.assertNotIn(">Commander<", source)
        self.assertNotIn(">Espace client<", source)

    def test_public_header_removes_primary_cta_inside_prospect_tunnel(self) -> None:
        source = template_source("components/nav/landing_header.html")

        self.assertIn('current_namespace != "prospects"', source)
        self.assertIn("Demander un accès", source)

    def test_portal_header_uses_role_focused_labels(self) -> None:
        header = template_source("components/nav/portal_header.html")
        client_nav = template_source("components/nav/portal_client_navigation.html")
        staff_nav = template_source("components/nav/portal_staff_navigation.html")
        profile = template_source("components/nav/portal_profile_menu.html")
        profile_icon = template_source("components/nav/profile_icon.html")
        create_menu = template_source("components/nav/portal_client_create_menu.html")
        create_icon = template_source("components/nav/creation_icon.html")
        portal_tags = app_source("apps/portal/templatetags/portal_tags.py")

        self.assertIn("Votre espace", client_nav)
        self.assertIn("Pilotage quotidien", staff_nav)
        self.assertIn("Administration Atelier", staff_nav)
        self.assertIn(">Tableau de bord</a>", staff_nav)
        self.assertIn(">Commandes</a>", staff_nav)
        self.assertIn("Outils Atelier", staff_nav)
        self.assertIn("Demandes d’accès", staff_nav)
        self.assertIn("Modèles d’e-mails", staff_nav)
        self.assertIn("Réglages de laize", staff_nav)
        self.assertIn("Votre compte", header)
        self.assertIn(">Atelier</span>", header)
        self.assertIn("product-menu-button__icon", header)
        self.assertIn("ui-btn ui-btn-ghost ui-btn-sm product-menu-button", header)
        self.assertIn("portal_profile_menu.html", header)
        self.assertIn("portal_navigation_access as portal_nav_access", header)
        self.assertIn("product-nav__brand", header)
        self.assertIn("product-nav__account", header)
        self.assertIn("product-profile__trigger", profile)
        self.assertIn("product-nav__chevron", profile)
        self.assertIn("product-profile__menu", profile)
        self.assertIn("Mon compte", profile)
        self.assertIn("Mes informations", profile)
        self.assertIn("Se déconnecter", profile)
        self.assertNotIn("Voir le site", profile)
        self.assertNotIn("product-profile__trigger-copy", profile)
        product_css = static_source("css/components/product-shell.css")
        self.assertIn("body.product-shell .product-nav__chevron", product_css)
        self.assertIn("flex: 0 0 auto", product_css)
        self.assertNotIn("max-width: 9.5rem", product_css)
        self.assertIn("{% csrf_token %}", profile)
        self.assertIn("request.user.is_staff and perms.accounts.access_staff_portal", profile)
        self.assertIn("portal:client-team", profile)
        self.assertIn("portal:staff-dashboard", profile)
        self.assertIn("portal:logout", profile)
        self.assertIn("portal:profile", profile)
        self.assertIn("data-product-nav-details", profile)
        self.assertIn("portal_nav_access.can_manage_team", profile)
        self.assertEqual(profile_icon.count("<svg"), 4)
        self.assertEqual(profile_icon.count('aria-hidden="true"'), 4)
        self.assertIn("Créer une commande", create_menu)
        self.assertIn("À partir de fichiers", create_menu)
        self.assertIn("Composer une planche DTF", create_menu)
        self.assertIn("Créer une planche DTF", create_menu)
        self.assertIn("portal:client-order-project-create", create_menu)
        self.assertIn("portal:client-gang-sheet-list-create", create_menu)
        self.assertIn("cash_checkout_requires_gang_sheet", create_menu)
        self.assertIn("data-product-nav-details", create_menu)
        self.assertEqual(create_icon.count("<svg"), 2)
        self.assertIn("def portal_navigation_access", portal_tags)
        self.assertIn("cash_checkout_requires_gang_sheet", portal_tags)
        self.assertIn("get_customer_membership", portal_tags)
        self.assertIn("portal_client_navigation.html", header)
        self.assertIn("portal_staff_navigation.html", header)
        self.assertIn("data-product-nav-details", staff_nav)
        self.assertIn('aria-current="page"', client_nav)
        self.assertIn('aria-current="page"', staff_nav)
        self.assertNotIn("Pilotage staff", header)
        self.assertNotIn("btn-nav-cta", header)
        self.assertNotIn('class="btn', header)
        self.assertNotIn("x-data", header)
        self.assertNotIn("@click", header)
        self.assertNotIn(">Équipe</a>", client_nav)

    def test_client_navigation_hides_project_tools_without_customer_eligibility(self) -> None:
        source = template_source("components/nav/portal_client_navigation.html")
        create_menu = template_source("components/nav/portal_client_create_menu.html")

        self.assertIn("client-gang-sheet-list-create", source)
        self.assertIn("portal_nav_access.project_creation_enabled", source)
        self.assertIn("portal_nav_access.project_creation_enabled", create_menu)
        self.assertNotIn("{% if b2b_order_projects_globally_enabled %}", source)

    def test_account_and_gang_sheet_libraries_use_task_focused_layouts(self) -> None:
        profile = template_source("portal/profile.html")
        team = template_source("portal/client/team.html")
        account_rail = template_source("components/portal/account_rail.html")
        gang_library = template_source("portal/client/gang_sheets/list.html")
        form_actions = template_source("components/forms/form_actions.html")

        identity = template_source("portal/partials/profile_identity_display.html")
        identity_form = template_source("portal/partials/profile_identity_form.html")

        self.assertIn("account-profile-layout", profile)
        self.assertIn("components/portal/account_rail.html", profile)
        self.assertIn("profile_identity_display.html", profile)
        self.assertIn("components/portal/page_head.html", profile)
        self.assertIn("subtitle=", profile)
        self.assertNotIn("page-head__eyebrow", profile)
        self.assertNotIn("kicker=", profile)
        self.assertNotIn('x-on:input="dirty = true"', profile)
        self.assertNotIn("primary_disabled_until_dirty=1", profile)
        self.assertNotIn("account-profile-lock-badge", profile)
        self.assertIn("id_login_email", identity_form)
        self.assertIn('hx-swap="outerHTML"', identity)
        self.assertIn("portal:profile-identity", identity)
        self.assertIn("account-profile-facts", identity)
        self.assertIn("company_profile_display.html", profile)
        self.assertIn("account-profile-page", team)
        self.assertIn('account_section="team"', team)
        self.assertNotIn("kicker=", team)
        self.assertIn("components/portal/account_rail.html", team)
        self.assertIn("components/ui/empty_state.html", team)
        self.assertIn("portal:profile", account_rail)
        self.assertIn("account-profile-rail-name", account_rail)
        self.assertIn("portal:client-team", account_rail)
        self.assertIn('x-bind:disabled="!dirty"', form_actions)
        self.assertIn("portal-page--client", gang_library)
        self.assertIn("components/portal/page_head.html", gang_library)
        self.assertIn("client_gang_sheets_list.html", gang_library)
        self.assertIn("gang-sheet-toolbar", gang_library)
        self.assertIn('id="create-gang-sheet-dialog"', gang_library)
        self.assertIn("data-dialog-auto-open", gang_library)
        self.assertIn("data-status-group", gang_library)
        self.assertIn("?display=inline", gang_library)
        self.assertNotIn('class="gang-workflow"', gang_library)
        self.assertNotIn("Créer une planche autonome", gang_library)

    def test_client_portal_hardening_keeps_actions_named_and_contrasted(self) -> None:
        dashboard = template_source("portal/client/dashboard.html")
        editor = template_source("portal/client/gang_sheets/editor.html")
        team = template_source("portal/client/team.html")
        invite_panel = template_source("portal/client/partials/team_invite_panel.html")
        deactivate = template_source("portal/client/partials/team_member_deactivate_button.html")
        revoke = template_source("portal/client/partials/team_invitation_revoke_button.html")
        product_css = static_source("css/components/product-shell.css")
        gang_css = static_source("css/components/gang-sheet.css")
        studio_css = static_source("css/components/gang-sheet-studio.css")

        self.assertIn('head_labelledby="client-dashboard-title"', dashboard)
        self.assertIn("components/portal/page_head.html", dashboard)
        self.assertIn('title="Tableau de bord"', dashboard)
        self.assertIn('id="client-volume-discount-title">', dashboard)
        self.assertIn("client-dashboard-palier__meter", dashboard)
        self.assertEqual(editor.count('aria-label="Étape '), 4)
        self.assertIn("— Studio — Prenium DTF", editor)
        self.assertIn("display: block", studio_css)
        self.assertIn(
            ".product-date-picker__trigger [data-date-display].is-placeholder {\n"
            "    color: var(--product-muted);",
            product_css,
        )
        self.assertIn("--product-danger-text: #9f1239", product_css)
        self.assertIn("color: var(--product-danger-text", gang_css)
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", product_css)
        self.assertIn("team_member_deactivate_button.html", team)
        self.assertIn("team_invitation_revoke_button.html", invite_panel)
        for dialog_source in [deactivate, revoke]:
            self.assertIn('aria-haspopup="dialog"', dialog_source)
            self.assertIn("data-dialog-open", dialog_source)
            self.assertIn("data-dialog-close", dialog_source)
            self.assertIn("{% csrf_token %}", dialog_source)

    def test_gang_sheet_editor_behaves_like_a_responsive_production_studio(self) -> None:
        editor = template_source("portal/client/gang_sheets/editor.html")
        canvas_css = static_source("css/components/gang-sheet.css")
        studio_css = static_source("css/components/gang-sheet-studio.css")
        runtime = static_source("js/gang-sheet-editor.js")
        studio_entrypoint = static_source("css/entries/studio.css")

        self.assertIn("gang-editor__progress-row", editor)
        self.assertIn('data-mobile-panel-tab="canvas"', editor)
        self.assertIn("data-zoom-reset", editor)
        self.assertIn("data-status-detail", editor)
        self.assertIn("data-gang-crop-box", editor)
        self.assertIn('name="crop_manifest"', editor)
        self.assertIn("Recadrage non destructif", editor)
        self.assertIn("data-crop-manual", editor)
        self.assertIn("data-crop-auto", editor)
        self.assertIn("Espacement auto-imposition", editor)
        self.assertIn("data-spacing-x", editor)
        self.assertIn("data-spacing-y", editor)
        self.assertIn("data-apply-spacing", editor)
        self.assertIn("data-alignment-panel", editor)
        self.assertIn('value="selection" data-align-reference', editor)
        self.assertIn('value="sheet" data-align-reference', editor)
        for direction in ["left", "center-x", "right", "top", "center-y", "bottom"]:
            self.assertIn(f'data-align="{direction}"', editor)
        self.assertNotIn("Répétition", editor)
        self.assertNotIn("data-grid-rows", editor)
        self.assertNotIn("Créer la grille", editor)
        self.assertIn("gang-validation-heading", editor)
        self.assertIn("data-sheet-quantity", editor)
        self.assertIn("Exemplaires de planche", editor)
        self.assertIn("data-sheet-order-quote", editor)
        self.assertIn("data-sheet-quantity", runtime)
        self.assertIn("updateOrderQuoteUi", runtime)
        self.assertIn("function syncCreateOrderProjectControl", runtime)
        self.assertIn('link.removeAttribute("aria-disabled")', runtime)
        self.assertIn("root.dataset.createOrderFormUrl", runtime)
        self.assertIn('state.status === "validated"', runtime)
        self.assertIn('@import "../components/gang-sheet-studio.css"', studio_entrypoint)
        self.assertIn("height: max(40rem, calc(100dvh - 6.5rem))", studio_css)
        self.assertNotIn("body.product-shell:has(.gang-editor) .app-main", studio_css)
        self.assertNotIn("width: min(96rem", studio_css)
        product_shell = static_source("css/components/product-shell.css")
        self.assertIn("product-shell--studio", product_shell)
        self.assertIn("width: min(1540px, calc(100vw - 1.5rem))", product_shell)
        self.assertIn("product-shell--studio", editor)
        self.assertIn("[data-editor-panel].is-mobile-active", studio_css)
        self.assertIn("min-height: 2.75rem", studio_css)
        self.assertIn("function setMobilePanel", runtime)
        self.assertIn("function renderZoom", runtime)
        self.assertIn("function startCropPointerAction", runtime)
        self.assertIn("function detectPreviewAutoCrop", runtime)
        self.assertIn('mode: cropModes[index] || "manual"', runtime)
        self.assertIn('new CustomEvent("b2b:preview-file-request"', runtime)
        self.assertIn("min-height: 0", canvas_css)
        self.assertGreaterEqual(canvas_css.count("box-sizing: content-box"), 2)
        self.assertNotIn("min-height: 9.375rem", canvas_css)
        self.assertIn(
            ".gang-sheet-item__preview { position: absolute; inset: 0; overflow: hidden;",
            canvas_css,
        )
        self.assertIn(
            ".gang-sheet-item__preview img { position: absolute; top: 50%; left: 50%;",
            canvas_css,
        )
        self.assertIn("function resizeItemFromPointer", runtime)
        self.assertIn("item.height_mm = Math.max(1, round(start.height + deltaX))", runtime)
        self.assertIn("function renderSelectedItemToolbar", runtime)
        self.assertIn('attribute: "data-canvas-rotate-item"', runtime)
        self.assertIn('attribute: "data-canvas-delete-item"', runtime)
        self.assertIn("function spacingRequestBody", runtime)
        self.assertIn("function autoPlaceWithSpacing", runtime)
        self.assertIn('body.append("spacing_x_mm", spacingX)', runtime)
        self.assertIn('body.append("spacing_y_mm", spacingY)', runtime)
        self.assertIn("let selectedIds = new Set()", runtime)
        self.assertIn("function selectionBounds", runtime)
        self.assertIn("function alignmentBounds", runtime)
        self.assertIn("function alignSelectedItems", runtime)
        self.assertIn('effectiveAlignmentReference() !== "selection"', runtime)
        self.assertIn("event.shiftKey || event.ctrlKey || event.metaKey", runtime)
        self.assertIn("item.x_mm = round(centerX - size.width / 2)", runtime)
        self.assertIn("item.y_mm = round(centerY - size.height / 2)", runtime)
        self.assertNotIn("function createSelectedGrid", runtime)
        self.assertNotIn('attribute: "data-canvas-repeat-item"', runtime)
        self.assertIn(".gang-sheet-item-toolbar", studio_css)
        self.assertIn(".gang-spacing-panel", studio_css)
        self.assertIn(".gang-spacing-grid", studio_css)
        self.assertIn(".gang-alignment-panel", studio_css)
        self.assertIn(".gang-alignment-reference", studio_css)
        self.assertIn(".gang-alignment-actions", studio_css)
        self.assertIn(".gang-sheet-item.is-primary .gang-sheet-item__resize", studio_css)
        self.assertIn(
            "translate(-50%, -50%) rotate(${item.rotation}deg)",
            runtime,
        )
        self.assertIn('window.addEventListener("beforeunload"', runtime)
        self.assertIn("root.dataset.dirty = String(dirty)", runtime)

    def test_gang_sheet_editor_exposes_safe_precision_tools(self) -> None:
        editor = template_source("portal/client/gang_sheets/editor.html")
        studio_css = static_source("css/components/gang-sheet-studio.css")
        runtime = static_source("js/gang-sheet-editor.js")

        for marker in [
            "data-undo-layout",
            "data-redo-layout",
            "data-snap-toggle",
            "data-select-all",
            "data-touch-multiselect",
            "data-delete-selected",
            "data-batch-delete-url",
            "data-canvas-clear-zone",
            "data-canvas-scroll",
            "gang-sheet-canvas-scroll",
            'data-distribute="horizontal"',
            'data-distribute="vertical"',
            "data-selection-gap",
            'data-apply-selection-gap="horizontal"',
            'data-apply-selection-gap="vertical"',
            "data-issues-list",
        ]:
            self.assertIn(marker, editor)

        for marker in [
            "function layoutSnapshot",
            "function commitLayoutMutation",
            "function undoLayoutMutation",
            "function redoLayoutMutation",
            "function resetLayoutHistory",
            "function calculateSnapForMove",
            "function renderSnapGuides",
            "function startRectangleSelection",
            "function canStartRectangleSelection",
            "function pointerToCanvasPx",
            "function toggleTouchMultiSelect",
            "function distributeSelectedItems",
            "function applyPreciseGap",
            "function groupSelectedItems",
            "function ungroupSelectedItems",
            "function translateSelectionAsGroup",
            "function focusIssue",
            "function fixOverflowIssue",
        ]:
            self.assertIn(marker, runtime)

        self.assertIn('value="others" data-align-reference', editor)
        self.assertIn("data-group-selection", editor)
        self.assertIn("data-multi-inspector", editor)
        self.assertIn("data-rotate-selection", editor)
        self.assertIn("data-ungroup-selection", editor)
        self.assertIn('name="lock"', editor)
        self.assertIn('name="unlock"', editor)
        self.assertIn("layout_group_id", runtime)
        self.assertIn("function renderSelectionGroupToolbar", runtime)
        self.assertIn("data-canvas-group-selection", runtime)
        self.assertIn("data-canvas-ungroup-selection", runtime)
        self.assertIn("function createLockIcon", runtime)
        self.assertIn('attribute: "data-canvas-rotate-item"', runtime)
        self.assertIn("item.rotation = (Number(item.rotation) + 90) % 360", runtime)
        self.assertIn("nextCenterX = centerX + dy", runtime)
        self.assertIn("nextCenterY = centerY - dx", runtime)
        self.assertIn("Groupe de ${items.length} visuels pivoté de 90°.", runtime)
        self.assertIn("gang-selection-frame__chrome", runtime)
        self.assertIn("${countLabel} · ${widthCm}", runtime)
        self.assertIn("preferBelow: true", runtime)
        self.assertIn('label: "Pivoter"', runtime)
        self.assertIn('label: "Supprimer"', runtime)
        self.assertIn('label: "Grouper"', runtime)

        self.assertIn("const HISTORY_LIMIT = 40", runtime)
        self.assertIn("function syncLayoutDirtyState", runtime)
        self.assertIn("layoutSignature() !== savedLayoutSignature", runtime)
        self.assertIn("resetLayoutHistory();", runtime)
        self.assertIn("focus.dataset.issueFocus", runtime)
        self.assertIn("fix.dataset.issueFix", runtime)
        self.assertIn('window.addEventListener("pointercancel", cancel)', runtime)
        self.assertIn('event.key.toLowerCase() === "y"', runtime)
        self.assertIn("async function deleteSelected", runtime)
        self.assertIn("root.dataset.batchDeleteUrl", runtime)
        self.assertIn("window.confirm", runtime)
        self.assertIn("suppressNextCanvasClick", runtime)
        self.assertIn("function clearSelectionFromCanvasBackground", runtime)
        self.assertIn('q("[data-canvas-clear-zone]")', runtime)
        self.assertIn(".gang-snap-guide", studio_css)
        self.assertIn(
            'canvasClearZone.addEventListener("pointerdown", startRectangleSelection)',
            runtime,
        )
        self.assertIn("function canStartRectangleSelection", runtime)
        self.assertIn(".gang-selection-marquee", studio_css)
        self.assertIn(".gang-editor__history", studio_css)
        self.assertIn(".gang-editor__selection-tools", studio_css)
        self.assertIn(".gang-editor__touch-multiselect", studio_css)
        self.assertIn(".gang-issue-fix", studio_css)
        self.assertIn(".gang-selection-delete", studio_css)

    def test_portal_navigation_closes_secondary_tools_accessibly(self) -> None:
        runtime = static_source("js/product-shell.js")

        self.assertIn("closeProductNavDetails", runtime)
        self.assertIn('event.key === "Escape"', runtime)
        self.assertIn("restoreFocus && containedFocus", runtime)
        self.assertIn('details.removeAttribute("open")', runtime)
        self.assertIn("data-product-nav-details", runtime)

    def test_portal_header_and_lists_share_the_tablet_breakpoint(self) -> None:
        header = template_source("components/nav/portal_header.html")
        orders = template_source("components/tables/orders_table.html")
        projects = template_source("portal/client/order_projects_list.html")
        product_css = static_source("css/components/product-shell.css")
        shell_css = static_source("css/components/shell.css")

        self.assertNotIn("md:!hidden", header)
        self.assertNotIn("md:flex", header)
        self.assertIn("@media (max-width: 959px)", product_css)
        self.assertNotIn("body.product-shell .ui-data-table thead th", product_css)
        self.assertIn("body.product-shell .ui-data-table th", shell_css)
        self.assertIn("top: 0", shell_css)
        # Visibilité table/cartes : Tailwind + règles product-shell (960px).
        self.assertIn(".ui-orders-table-desktop", product_css)
        self.assertIn(".ui-orders-list-mobile", product_css)
        self.assertIn("display: none !important", product_css)
        self.assertIn(
            "body.product-shell .ui-orders-table-desktop .ui-order-primary__label",
            product_css,
        )
        self.assertIn("ui-orders-table-desktop", orders)
        self.assertIn("ui-orders-list-mobile", orders)
        self.assertIn("min-[960px]:block", orders)
        self.assertIn("min-[960px]:hidden", orders)
        self.assertIn("ui_order_projects_table", projects)
        projects_table = template_source("components/tables/order_projects_table.html")
        self.assertIn("ui-orders-table-desktop", projects_table)
        self.assertIn("ui-orders-list-mobile", projects_table)
        self.assertIn("min-[960px]:block", projects_table)
        self.assertIn("min-[960px]:hidden", projects_table)
        customers = template_source("portal/staff/customers/list.html")
        self.assertIn("min-[960px]:block", customers)
        self.assertIn("min-[960px]:hidden", customers)

        for path in [
            "portal/client/partials/checkout_uploads.html",
            "portal/client/panels/uploads.html",
            "portal/staff/panels/uploads.html",
        ]:
            with self.subTest(path=path):
                upload_table = template_source(path)
                self.assertIn("min-[960px]:block", upload_table)
                self.assertIn("min-[960px]:hidden", upload_table)

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
        self.assertIn("ui-brand-lockup__home", logo)
        self.assertIn("Prenium DTF", logo)
        self.assertIn("via IDS supply", logo)
        self.assertIn("brand_home_url as resolved_brand_home_url", logo)
        self.assertIn("brand_home_href", template_source("components/nav/portal_header.html"))
        portal_header = template_source("components/nav/portal_header.html")
        landing_header = template_source("components/nav/landing_header.html")
        self.assertIn("portal:client-dashboard", portal_header)
        self.assertIn("portal:staff-dashboard", portal_header)
        self.assertIn("product-header", landing_header)
        self.assertIn("ui-foundation-nav", landing_header)
        self.assertNotIn("{% url 'home' %}", logo)
        self.assertIn("body .ui-brand-lockup__name", legacy_css)
        self.assertIn("body .ui-brand-lockup__subtitle", legacy_css)
        for header in headers:
            self.assertIn('include "components/brand/logo.html"', header)

    def test_login_hides_internal_roles_and_keeps_only_useful_copy(self) -> None:
        source = template_source("portal/login.html")

        self.assertIn("product-login-card__intro", source)
        self.assertNotIn("product-login-heading", source)
        self.assertIn("Retrouvez vos commandes, vos fichiers et vos documents", source)
        self.assertIn("Demander un accès professionnel", source)
        for forbidden in ["client", "staff", "backend", "permissions", "droits"]:
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())

    def test_staff_dashboard_uses_french_premium_copy(self) -> None:
        source = staff_dashboard_markup()

        self.assertNotIn("kicker=", source)
        self.assertIn('title="Tableau de bord"', source)
        self.assertNotIn("atelier-next-action", source)
        self.assertNotIn("Prochain geste", source)
        self.assertIn("ui_kpi_grid", source)
        self.assertIn("atelier-dashboard-metrics", source)
        self.assertNotIn('class="portal-page-surface atelier-dashboard-metrics', source)
        self.assertIn("atelier-dashboard-stack", source)
        self.assertNotIn('class="atelier-dashboard-panel"', source)
        self.assertNotIn("ui_list_tabs", source)
        self.assertIn("ui_atelier_worklist_table", source)
        worklist_table = template_source("components/tables/atelier_worklist_table.html")
        self.assertIn("ui-orders-table-desktop", worklist_table)
        self.assertIn("ui-data-table", worklist_table)
        self.assertIn("ui-mobile-order-card", worklist_table)
        self.assertNotIn("atelier-order-list", source)
        self.assertNotIn("atelier-worklist__legend", source)
        self.assertIn("atelier-worklist-command", source)
        self.assertIn("ui-list-command--compact", source)
        self.assertIn("ui-list-command", source)
        self.assertNotIn("atelier-worklist-results", source)
        self.assertIn("files_to_process_label", worklist_table)
        self.assertNotIn("Contrôle dans le pilotage", worklist_table)
        self.assertNotIn(">Production<", worklist_table)
        self.assertIn("is-batch-selected", worklist_table)
        kpi_grid = template_source("components/tables/kpi_grid.html")
        self.assertIn("ui-kpi-card--filter", kpi_grid)
        self.assertIn("card_href", kpi_grid)
        self.assertNotIn("<svg", source)
        dashboard_css = static_source("css/components/product-shell.css")
        self.assertNotIn("--product-paper", dashboard_css)
        self.assertIn("Imprimer le lot", source)
        self.assertIn('value="all_unprinted"', source)
        self.assertIn("data-atelier-batch", source)
        self.assertIn('id="atelier-dashboard-panel"', source)
        self.assertIn("atelier-dashboard-batch.js", template_source("portal/staff/dashboard.html"))
        self.assertNotIn("Imprimer tous les OF prêts", source)
        self.assertNotIn("atelier-worklist__batch-more", source)
        portal_core = static_source("css/entries/portal-core.css")
        portal_staff = static_source("css/entries/portal-staff.css")
        self.assertNotIn(".staff-data-list__mobile\n) {", portal_core)
        self.assertIn(
            ".portal-page-surface.ui-list-section .staff-data-list__mobile",
            portal_core,
        )
        self.assertIn(
            "display: none !important",
            portal_core.split("staff-data-list__mobile")[-1][:400],
        )
        self.assertIn(
            ".portal-page-surface.ui-list-section .staff-data-list__mobile",
            portal_staff,
        )
        self.assertNotIn("Accès rapides Atelier", source)
        self.assertNotIn("Contrats permissions", source)
        self.assertNotIn("Accès commandes autorisé", source)
        self.assertNotIn("Accueil staff", source)
        self.assertNotIn("Backoffice staff", source)

    def test_staff_navigation_keeps_accounts_in_primary_only(self) -> None:
        staff_nav = template_source("components/nav/portal_staff_navigation.html")

        self.assertIn(">Comptes</a>", staff_nav)
        self.assertEqual(staff_nav.count("portal:staff-customer-list"), 1)
        self.assertNotIn("Comptes clients", staff_nav)

    def test_staff_views_distill_secondary_actions_and_repeated_information(self) -> None:
        order = template_source("portal/staff/order_detail.html")
        access_list = template_source("portal/staff/access_requests/list.html")
        access_detail = template_source("portal/staff/access_requests/detail.html")
        machine_fleet = template_source("portal/staff/machines/_fleet_content.html")
        discount_settings = template_source("portal/staff/customers/default_volume_discounts.html")
        billing = template_source("portal/staff/panels/billing.html")
        project = template_source("portal/staff/order_project_detail.html")

        self.assertNotIn("staff-order-focus__eyebrow", order)
        self.assertEqual(order.count("staff_order_focus.review_label"), 1)
        self.assertNotIn("staff_order_focus.production_label", order)
        self.assertNotIn("Résultats affichés", access_list)
        self.assertIn('<details class="staff-access-panel access-review-reject"', access_detail)
        self.assertIn('<details class="machine-fleet-create"', machine_fleet)
        self.assertIn('<details class="volume-tier-create-card"', discount_settings)
        self.assertNotIn("<span>Paiement</span>", billing)
        self.assertNotIn("<span>Justificatif</span>", billing)
        self.assertIn("staff-project-item-list", project)
        self.assertIn("components/portal/breadcrumbs/staff_order_project_detail.html", project)
        self.assertNotIn("staff-project-detail__back", project)
        self.assertNotIn("Sprint 4", project)

    def test_staff_inspection_uses_compact_summary_without_nested_metric_cards(self) -> None:
        source = template_source("portal/staff/panels/inspection.html")
        portal_entry = static_source("css/entries/portal-staff.css")
        inspection_css = static_source("css/components/inspection-workbench.css")

        self.assertNotIn("atelier-inspection__summary", source)
        self.assertNotIn("Priorité de contrôle", source)
        self.assertIn("pending_review_count", source)
        self.assertIn("approved_review_count", source)
        self.assertIn("Analyse automatique", source)
        self.assertIn("Décision Atelier", source)
        self.assertIn("Action requise", source)
        self.assertIn("Le client sera notifié par e-mail", source)
        self.assertIn('class="atelier-inspection__review-grid"', source)
        self.assertLess(
            source.index('class="atelier-inspection__review-grid"'),
            source.index('class="atelier-inspection__correction"'),
        )
        self.assertGreater(
            source.index('class="atelier-inspection__correction"'),
            source.index("</div>", source.index('class="atelier-inspection__review-grid"')),
        )
        self.assertIn('@import "../components/inspection-workbench.css";', portal_entry)
        self.assertIn(".atelier-inspection__review-block--decision", inspection_css)
        self.assertIn("minmax(0, 1.18fr)", inspection_css)
        self.assertIn(".atelier-inspection__correction .ui-input", inspection_css)
        self.assertIn(".atelier-inspection__correction select.ui-input", portal_entry)
        self.assertIn("@media (max-width: 639px)", inspection_css)
        self.assertIn("@media (prefers-reduced-motion: reduce)", inspection_css)
        self.assertIn("Facultatif, sauf si le motif est", source)
        self.assertNotIn("font-display text-2xl", source)
        self.assertNotIn("uppercase tracking-wide", source)

    def test_staff_order_panels_keep_one_status_and_disclose_secondary_detail(self) -> None:
        tabs = template_source("components/order/order_tabs.html")
        production = template_source("portal/staff/panels/production.html")
        operations = template_source("portal/staff/operations/index.html")
        shipping = template_source("portal/staff/panels/shipping.html")
        billing = template_source("portal/staff/panels/billing.html")

        self.assertIn("workflow-shell--distilled", tabs)
        self.assertIn("workflow-shell--tabs-{{ tabs|length }}", tabs)
        self.assertIn("workflow-progress__label", tabs)
        self.assertNotIn("Avancement de l’OF", production)
        self.assertNotIn("operator-reference-bar", production)
        self.assertIn("show_machine_workspace", production)
        self.assertIn("require_machine_selection", production)
        self.assertLess(
            production.index("Sélection machine"),
            production.index("Métrage de production"),
        )
        self.assertLess(
            production.index("Métrage de production"),
            production.index('id="operator-print-title"'),
        )
        self.assertIn("workflow-disclosure production-meterage", production)
        self.assertIn("workflow-disclosure production-history", production)
        self.assertIn("operationScan.focus", operations)
        self.assertNotIn("Utiliser l’OF de cette commande", operations)
        self.assertNotIn("shipping-readiness", shipping)
        self.assertIn("Suivi Sendcloud", shipping)
        self.assertIn("billing-total", billing)
        self.assertIn("workflow-disclosure billing-breakdown", billing)
        self.assertNotIn("Pièces de la commande", billing)

    def test_staff_order_detail_flattens_nested_workflow_borders(self) -> None:
        product_css = static_source("css/components/product-shell.css")
        detail = template_source("portal/staff/order_detail.html")

        self.assertIn("staff-order-detail-stack", detail)
        self.assertIn(
            "body.product-shell .staff-order-detail-stack .ui-workflow-shell",
            product_css,
        )
        self.assertIn(
            "body.product-shell .staff-order-detail-stack .ui-panel-shell",
            product_css,
        )
        self.assertIn(
            "body.product-shell .staff-order-detail-stack .workflow-panel-target",
            product_css,
        )
        self.assertIn(
            "body.product-shell .staff-order-detail-stack .workflow-panel-target",
            product_css,
        )
        # Surfaces internes plates (pas de re-pile d’ombres dures).
        self.assertGreaterEqual(
            product_css.count("body.product-shell .staff-order-detail-stack .ui-panel-shell"),
            1,
        )
        self.assertIn(
            ".staff-order-detail-stack .workflow-panel-target,\n"
            "  body.product-shell .staff-order-detail-stack .workflow-panel,\n"
            "  body.product-shell .staff-order-detail-stack .workflow-form-card",
            product_css,
        )
        self.assertIn("box-shadow: none !important", product_css)

    def test_saas_button_system_is_imported_with_interaction_tokens(self) -> None:
        input_css = static_source("css/input.css")
        tokens_css = static_source("css/tokens.css")
        buttons_css = static_source("css/components/buttons.css")

        self.assertIn('@import "./components/buttons.css";', input_css)
        self.assertIn("--ui-action-min-h", tokens_css)
        self.assertIn("--ui-action-shadow: 3px 3px 0 var(--ink)", tokens_css)
        self.assertIn("--ui-action-secondary-border", tokens_css)
        self.assertIn(".ui-btn-primary", buttons_css)
        self.assertIn(".ui-btn-secondary", buttons_css)
        self.assertIn("box-shadow: var(--ui-action-shadow)", buttons_css)

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
            "prospects/confirmation.html",
            "prospects/verification_result.html",
            "portal/access/invitation_accept.html",
        ]

        for path in paths:
            if path == "portal/staff/dashboard.html":
                source = staff_dashboard_markup()
            else:
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
        self.assertIn("portal:client-order-project-create", client_results)
        self.assertIn("portal:client-gang-sheet-list-create", client_results)
        self.assertIn("default_billing_mode", client_results)
        self.assertIn("b2b_order_projects_globally_enabled", client_results)
        self.assertIn("portal:client-checkout", client_results)
        self.assertIn("client-orders-list-results", client_source)
        self.assertIn('hx-trigger="input changed delay:300ms, search"', client_source)
        self.assertIn("client_orders_list_results.html", client_source)
        self.assertIn("Retour au tableau de bord", staff_source)
        self.assertIn("portal-page-surface", staff_source)
        self.assertIn("ui-list-section", staff_source)
        self.assertNotIn('<section class="card">', staff_source)
        self.assertIn("portal:staff-dashboard", staff_source)
        self.assertIn("Aucune commande", staff_source)
        self.assertNotIn("Aucune commande a afficher.", staff_source)

    def test_portal_lists_share_pagination_and_form_action_partials(self) -> None:
        pagination_partial = 'include "components/portal/pagination.html"'
        for path in [
            "portal/client/partials/client_orders_list_results.html",
            "portal/staff/orders_list.html",
            "portal/staff/customers/list.html",
            "portal/staff/access_requests/list.html",
            "portal/client/order_projects_list.html",
            "portal/staff/order_projects_list.html",
            "portal/client/gang_sheets/list.html",
        ]:
            with self.subTest(path=path):
                self.assertIn(pagination_partial, template_source(path))

        customer_detail = template_source("portal/staff/customers/detail.html")
        self.assertEqual(
            customer_detail.count('include "components/forms/form_actions.html"'),
            2,
        )
        self.assertNotIn('class="form-actions"', customer_detail)

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
        operations = template_source("portal/staff/operations/_job_row.html")

        self.assertNotIn('class="card order-command-bar" style=', staff_detail)
        self.assertNotIn('class="card staff-customer-snapshot" style=', staff_customer)
        self.assertNotIn('class="workflow-kpi" style=', production)
        self.assertNotIn('class="production-track"', production)
        self.assertIn('class="workflow-disclosure production-history"', production)
        self.assertIn('class="atelier-operation-row', operations)
        self.assertIn("atelier-operation-workflow", operations)
        self.assertIn("workflow_hint", operations)
        self.assertNotIn("display: inline; margin-right", operations)

    def test_prospect_primary_actions_declare_button_hierarchy(self) -> None:
        paths = [
            "prospects/step1.html",
            "prospects/step2.html",
            "prospects/step3.html",
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
            "id_siren",
            "id_vat_number",
        ]:
            with self.subTest(field_id=field_id):
                self.assertIn(f'class="ui-label" for="{field_id}"', source)
                self.assertNotIn(f'class="ui-sr-only" for="{field_id}"', source)

        self.assertIn("<legend>{{ form.activity_type.label }}</legend>", source)
        self.assertIn('class="ui-field-error"', source)
        self.assertNotIn('class="error-text"', source)

    def test_b2b_order_project_flow_reuses_portal_htmx_contracts(self) -> None:
        detail = template_source("portal/client/order_project_detail.html")
        fields = template_source("portal/client/partials/order_project_fields.html")
        items = template_source("portal/client/partials/order_project_items.html")
        editor = template_source("portal/client/partials/order_project_visual_editor.html")
        replace_form = template_source(
            "portal/client/partials/order_project_replace_asset_form.html"
        )
        configurator_script = static_source("js/b2b-configurator.js")
        add_form = template_source("portal/client/partials/order_project_add_visual_form.html")
        validation_panel = template_source(
            "portal/client/partials/order_project_add_visual_validation_panel.html"
        )
        item_delete = template_source(
            "portal/client/partials/order_project_item_delete_button.html"
        )
        support_color = template_source(
            "portal/client/partials/order_project_support_color_field.html"
        )
        product_shell = static_source("css/components/product-shell.css")
        header = template_source("components/nav/portal_header.html")
        staff_navigation = template_source("components/nav/portal_staff_navigation.html")

        summary = template_source("portal/client/partials/order_project_summary.html")
        settlement = template_source("portal/client/partials/b2b_settlement_choice.html")
        checkout_summary = template_source("portal/client/partials/checkout_summary.html")

        self.assertNotIn("b2b_settlement_choice.html", summary)
        self.assertIn('name="billing_mode"', summary)
        self.assertIn("b2b_settlement_choice.html", checkout_summary)
        self.assertIn('default_billing_mode == "immediate"', settlement)
        self.assertIn('value="deferred"', settlement)
        self.assertIn("b2b-settlement-choice--locked", settlement)
        shipping = template_source("portal/client/partials/b2b_shipping_choice.html")
        self.assertIn("b2b-shipping-choice__options", shipping)
        self.assertIn("b2b-shipping-choice__price", shipping)
        self.assertIn('type="radio"', shipping)
        self.assertNotIn("is-selected", shipping)
        self.assertIn('hx-indicator="#portal-htmx-indicator"', shipping)

        self.assertIn("project_client_label", detail)
        self.assertIn("components/portal/page_head.html", detail)
        self.assertIn("breadcrumbs/client_order_project_detail.html", detail)
        self.assertIn("b2b-project-header", detail)
        self.assertNotIn("b2b-project-checkout-bar__meta", summary)
        self.assertNotIn("page-head__eyebrow", detail)
        self.assertNotIn("b2b-project-quote__eyebrow", summary)
        self.assertIn("b2b-project-checkout", summary)
        self.assertIn("b2b-project-checkout-actions", summary)
        self.assertIn("b2b-project-quote", summary)
        self.assertNotIn("Mode de règlement", summary)
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
        self.assertIn("{% if item.can_replace_asset %}", editor)
        self.assertNotIn("<summary>Remplacer le fichier", editor)
        self.assertIn("data-asset-replace-before-analysis", replace_form)
        self.assertIn("Disponible uniquement avant le démarrage", replace_form)
        self.assertIn("has-replace-before-analysis", editor)
        self.assertIn(":not(.has-replace-before-analysis)", product_shell)
        self.assertIn("projectDialogToRestore", configurator_script)
        self.assertIn("projectDialogCloseOnSuccess", configurator_script)
        self.assertIn('document.body.addEventListener("htmx:afterSettle"', configurator_script)
        self.assertIn('document.body.addEventListener("htmx:beforeRequest"', configurator_script)
        self.assertIn("findOpenVisualDialog", configurator_script)
        self.assertIn('removeAttribute("required")', configurator_script)
        self.assertIn("data-visual-confirm", editor)
        self.assertIn("dialog[id^='visual-dialog-']", configurator_script)
        self.assertNotIn("dialog[open][id^='visual-dialog-']", configurator_script)
        self.assertNotIn("Largeur (mm)", editor)
        self.assertIn('type="hidden" name="width_mm"', editor)
        self.assertIn("ui-btn ui-btn-danger", item_delete)
        validation_dimensions = template_source(
            "portal/client/partials/order_project_validation_dimensions_row.html"
        )
        quality_review = template_source("portal/client/partials/order_project_quality_review.html")
        self.assertNotIn("À valider", items)
        self.assertNotIn("get_analysis_status_display", items)
        self.assertNotIn("{% elif review.issues %}", quality_review)
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
        self.assertIn("order_project_item_delete_button.html", validation_panel)
        self.assertIn("order_project_item_delete_button.html", editor)
        self.assertIn("order_project_item_delete_button.html", items)
        self.assertIn("action='delete'", item_delete)
        self.assertIn("Supprimer", item_delete)
        self.assertIn("b2b-confirm-dialog", item_delete)
        self.assertIn("data-dialog-open", item_delete)
        self.assertIn("Supprimer ce visuel ?", item_delete)
        self.assertIn("Supprimer définitivement", item_delete)
        self.assertIn("{% csrf_token %}", item_delete)
        self.assertIn("hx-post", item_delete)
        self.assertNotIn("hx-confirm", item_delete)
        self.assertNotIn("Rotation autorisée", validation_panel)
        self.assertNotIn("Rotation autorisée", editor)
        self.assertNotIn("Rotation autorisée", add_form)
        self.assertIn("Aperçu en préparation", items)
        self.assertIn("is-analyzing", items)
        self.assertIn("order_project_analysis_loader.html", items)
        analysis_loader = template_source(
            "portal/client/partials/order_project_analysis_loader.html"
        )
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
        self.assertIn("b2b-preview-zoom--solo", preview_stage)
        self.assertIn("b2b-preview-chrome", preview_stage)
        self.assertIn("min(32rem, 58vh)", product_shell)
        self.assertIn(".b2b-preview-stage.is-zoomed", product_shell)
        self.assertIn("cursor: grab", product_shell)
        self.assertIn(".b2b-preview-stage.is-zoomed.is-panning", product_shell)
        dialog_stage_block = product_shell.split(
            "body.product-shell .b2b-configurator-dialog .b2b-preview-stage {"
        )
        self.assertGreaterEqual(len(dialog_stage_block), 2)
        for chunk in dialog_stage_block[1:]:
            block = chunk.split("}", 1)[0]
            self.assertNotIn("height: auto", block)
            self.assertNotIn("max-height: none", block)
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
        self.assertIn("data-support-color-thin-alert", support_color)
        self.assertNotIn("data-support-color-exact-required", support_color)
        self.assertIn("b2b-support-color__badge", support_color)
        self.assertIn("Aucune couleur n’est présélectionnée", support_color)
        self.assertIn("Aucune sélection", support_color)
        self.assertIn("Détails sous 0,5 mm détectés", support_color)
        self.assertIn("optimiser la base blanche", support_color)
        self.assertIn("améliorer le toucher", support_color)
        self.assertNotIn("Sans cette couleur", support_color)
        self.assertNotIn("légèrement visible si la couleur du textile", support_color)
        self.assertIn('required aria-required="true"', support_color)
        self.assertIn("b2b-swatch-btn", support_color)
        self.assertIn("b2b-swatch-btn--rainbow", support_color)
        self.assertNotIn(
            "disabled", support_color.split("data-support-color-multicolor", 1)[1].split(">", 1)[0]
        )
        self.assertIn("b2b_hex_color_swatch.html", support_color)
        hex_swatch = template_source("portal/client/partials/b2b_hex_color_swatch.html")
        self.assertIn("b2b-swatch-btn--custom", hex_swatch)
        self.assertIn("Ouvrir", items)
        self.assertIn("order_project_item_delete_button.html", items)
        self.assertIn("Supprimer", item_delete)
        self.assertNotIn("data-awaiting-validation", items)
        self.assertNotIn("Valider ces informations", items)
        self.assertIn("confirm-analysis", editor)
        self.assertIn('data-file-picker-dialog="add-visual-dialog"', items)
        self.assertNotIn('data-dialog-open="add-visual-dialog"', items)
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
        self.assertIn("updateSupportColorStatus", configurator_runtime)
        self.assertNotIn('applySupportColorPickerValue(fieldset, "#ffffff")', configurator_runtime)
        self.assertIn("applyPreviewZoom", configurator_runtime)
        self.assertIn("data-preview-zoom-in", configurator_runtime)
        self.assertIn("bindPreviewPanDrag", configurator_runtime)
        self.assertIn("is-panning", configurator_runtime)
        self.assertIn("[data-configurator-stage].is-zoomed", configurator_runtime)
        self.assertIn("dialog.showModal()", configurator_runtime)
        self.assertIn("openAutoOpenDialogs", configurator_runtime)
        self.assertIn("dismissAutoOpenDialog", configurator_runtime)
        self.assertIn("clearOrderProjectValidateQuery", configurator_runtime)
        self.assertIn("autoOpenedDialogs", configurator_runtime)
        self.assertIn("new DataTransfer()", configurator_runtime)
        self.assertIn("[data-add-visual-form]", configurator_runtime)
        self.assertNotIn("instanceof ParentNode", configurator_runtime)
        self.assertIn("openFilePickerBeforeDialog", configurator_runtime)
        self.assertIn('document.createElement("input")', configurator_runtime)
        self.assertIn('targetInput.dispatchEvent(new Event("change"', configurator_runtime)
        self.assertIn('file.type === "application/pdf"', configurator_runtime)
        self.assertIn("async function isPdfCompatibleIllustrator", configurator_runtime)
        self.assertIn("file.slice(0, 5).arrayBuffer()", configurator_runtime)
        self.assertIn(
            "declaredPdf || await isPdfCompatibleIllustrator(file)",
            configurator_runtime,
        )
        self.assertIn('typeof pdfDocument?.destroy === "function"', configurator_runtime)
        self.assertIn('typeof loadingTask?.destroy === "function"', configurator_runtime)
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
        self.assertIn("Gang Sheets", staff_navigation)
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
        self.assertIn('enctype="multipart/form-data"', start_form)
        self.assertIn("data-order-start-form", start_form)
        self.assertIn("data-order-start-pick-visual", start_form)
        self.assertIn("data-order-start-file", start_form)
        self.assertIn('name="file"', start_form)
        self.assertIn('name="requested_date"', start_form)
        self.assertIn("components/forms/product_date_field.html", start_form)
        self.assertNotIn('type="date"', start_form)
        date_field = template_source("components/forms/product_date_field.html")
        self.assertIn("data-product-date-picker", date_field)
        self.assertIn("Date souhaitée", start_form)
        self.assertIn('name="customer_comment"', start_form)
        self.assertIn("bindOrderStartPickVisual", configurator_runtime)
        self.assertIn("data-order-start-pick-visual", configurator_runtime)

    def test_p3_retired_agency_partials_and_panel_empty_states(self) -> None:
        for dead_partial in [
            TEMPLATES_DIR / "shop/partials/landing_team.html",
            TEMPLATES_DIR / "shop/partials/landing_contact.html",
        ]:
            with self.subTest(path=str(dead_partial)):
                self.assertFalse(dead_partial.exists())

        empty_partial = 'include "components/ui/empty_state.html"'
        for path in [
            "portal/client/panels/uploads.html",
            "portal/staff/panels/uploads.html",
            "portal/staff/panels/inspection.html",
            "portal/client/panels/inspection.html",
        ]:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn(empty_partial, source)
                self.assertNotIn('<div class="empty-state">', source)

        gang_editor = template_source("portal/client/gang_sheets/editor.html")
        self.assertNotIn("product-eyebrow", gang_editor)
        self.assertIn("b2b-dialog-kicker", gang_editor)

        operations = template_source("portal/staff/operations/index.html")
        self.assertNotIn("terracotta", operations)
        self.assertIn("atelier-operations-scan-bar", operations)

    def test_p3_polish_titles_empty_states_and_studio_spacing_labels(self) -> None:
        title_paths = [
            "portal/client/orders_list.html",
            "portal/client/gang_sheets/list.html",
            "portal/client/gang_sheets/editor.html",
            "portal/staff/settings/branding.html",
            "portal/staff/gang_sheets/settings.html",
            "portal/client/team.html",
        ]
        for path in title_paths:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertNotIn(" - Prenium DTF", source)
                self.assertNotIn(" — Atelier", source)

        editor = template_source("portal/client/gang_sheets/editor.html")
        self.assertIn("— Studio — Prenium DTF", editor)
        self.assertIn('class="ui-label" for="gang-spacing-x"', editor)
        self.assertNotIn('<label for="gang-spacing-x">Horizontal X <span>', editor)

        empty_partial = template_source("components/ui/empty_state.html")
        self.assertIn("cta_button_label", empty_partial)
        self.assertIn("cta_button_dialog", empty_partial)

        for path, needle in [
            ("portal/client/partials/order_project_items.html", "Aucun fichier joint"),
            ("portal/staff/order_project_detail.html", "Aucun fichier joint"),
            ("portal/client/panels/production.html", "components/ui/empty_state.html"),
            ("portal/staff/panels/drive_sync.html", "components/ui/empty_state.html"),
            ("portal/client/panels/shipping.html", "components/ui/empty_state.html"),
        ]:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn(needle, source)
                self.assertNotIn("Aucun visuel", source)

    def test_lot4_portal_header_nav_removes_parasite_borders(self) -> None:
        header = template_source("components/nav/portal_header.html")
        landing_header = template_source("components/nav/landing_header.html")
        portal_entry = static_source("css/entries/portal-core.css")

        self.assertIn("ui-nav-rail", header)
        self.assertIn("ui-nav-rail", landing_header)
        self.assertNotIn("ui-nav-panel", header)
        self.assertNotIn("ui-nav-panel", landing_header)
        self.assertIn(
            "v15 — Header portail : navigation fluide sans cadres parasites",
            portal_entry,
        )
        self.assertIn(".product-header .ui-foundation-nav .ui-nav-rail", portal_entry)
        self.assertIn(".product-header .ui-foundation-nav .product-profile__trigger", portal_entry)
        self.assertIn("border: 0 !important", portal_entry.split("v15 — Header portail")[-1])
