import re
from pathlib import Path

from django.core.paginator import Paginator
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[3]
CSS_DIR = BACKEND_DIR / "static_src" / "css"
TEMPLATES_DIR = BACKEND_DIR / "templates"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class UiFoundationSourceTests(SimpleTestCase):
    def test_foundation_tokens_use_warm_light_brand_palette_and_soft_depth(self) -> None:
        tokens = source(CSS_DIR / "tokens.css")
        owned_css = "\n".join(
            source(path)
            for path in [
                CSS_DIR / "tokens.css",
                CSS_DIR / "components" / "buttons.css",
                CSS_DIR / "components" / "forms.css",
                CSS_DIR / "components" / "shell.css",
            ]
        )

        for contract in [
            "color-scheme: light",
            "--bg: #f4f0e6",
            "--surface: #fbf6ee",
            "--ink: #1a1815",
            "--muted: #6b675c",
            "--line: #e2dccb",
            "--brand: #ff8775",
            "--accent: #a83bc4",
            "--radius: 16px",
            "--radius-lg: 18px",
            "--ui-action-min-h: 2.75rem",
            "--ui-action-radius: 999px",
            "--ui-action-border-width: 2px",
            "--ui-action-shadow: 3px 3px 0 var(--ink)",
            '--ui-font-display: "Space Grotesk"',
            '--ui-font-body: "DM Sans"',
        ]:
            with self.subTest(contract=contract):
                self.assertIn(contract, tokens)

        self.assertNotIn("gradient(", owned_css)
        self.assertIn("--shadow-soft: 0 8px 24px", tokens)
        self.assertIn("box-shadow: var(--ui-action-shadow)", owned_css)

    def test_buttons_and_forms_keep_interaction_states_and_touch_targets(self) -> None:
        buttons = source(CSS_DIR / "components" / "buttons.css")
        forms = source(CSS_DIR / "components" / "forms.css")

        for marker in [
            ".ui-btn-primary",
            ".ui-btn-secondary",
            ".btn-saas-secondary",
            ".dui-btn-secondary",
            ".ui-btn-danger",
            ".ui-btn.is-loading",
            '[aria-disabled="true"]',
            ":focus-visible",
            "min-height: var(--ui-action-min-h)",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, buttons)

        for marker in [
            '.ui-input[aria-invalid="true"]',
            ".ui-input:disabled",
            ".ui-input:focus-visible",
            "min-height: var(--ui-action-min-h)",
            "@media (max-width: 639px)",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, forms)

        authoritative_secondary = buttons.split(
            'html[data-theme="prenium"] body.product-shell :is(', 1
        )[1]
        for alias in [
            ".ui-btn-secondary",
            ".btn-secondary",
            ".btn-saas-secondary",
            ".dui-btn-secondary",
        ]:
            with self.subTest(alias=alias):
                self.assertIn(alias, authoritative_secondary)
        self.assertIn(":is(.ui-btn-ghost, .dui-btn-ghost)", buttons)
        self.assertIn("background: transparent", buttons)
        self.assertIn("box-shadow: none", buttons)

    def test_toast_stack_uses_operate_tokens_not_daisy_alerts(self) -> None:
        feedback = source(CSS_DIR / "components" / "feedback.css")
        portal_core = source(CSS_DIR / "entries" / "portal-core.css")
        toast_tpl = source(TEMPLATES_DIR / "components" / "ui" / "toast_stack.html")
        toast_js = source(BACKEND_DIR / "static_src" / "js" / "alpine" / "toast-boot.js")

        self.assertIn('class="ui-toast-stack"', toast_tpl)
        self.assertIn('class="ui-toast"', toast_tpl)
        self.assertIn("ui-toast__mark", toast_tpl)
        self.assertNotIn("alert--", toast_tpl)
        self.assertNotIn("dui-alert", toast_tpl)
        self.assertNotIn("shadow-lg", toast_tpl)

        for marker in [
            ".ui-toast--success",
            ".ui-toast--error",
            ".ui-toast--warning",
            ".ui-toast--info",
            "border-radius: var(--radius-sm)",
            "var(--success)",
            "var(--danger)",
            "var(--shadow-soft)",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, feedback)

        self.assertIn(".ui-toast--success", portal_core)
        self.assertIn("ui-toast--success", toast_js)
        self.assertIn("ui-toast--error", toast_js)
        self.assertNotIn("alert--success", toast_js)

    def test_base_body_starts_with_finish_contract(self) -> None:
        base = source(TEMPLATES_DIR / "base.html")
        body = base.split('<body class="{% block body_class %}{% endblock %}">', 1)[1]
        contract = body.split("-->", 1)[0]
        expected_blocks = [
            "THESIS:",
            "OWN-WORLD:",
            "STORY:",
            "FIRST VIEWPORT:",
            "FORM: Bright embroidery workbench; user-pinned Octostitch color reference; "
            "seed key user-pinned-20260823.",
            "FINISH: unreviewed and undocumented is unfinished; this build ends with "
            "the finish review, the verdict, DESIGN.md, and every shipping raster "
            "carrying its provenance",
        ]

        self.assertTrue(body.startswith("<!--"))
        positions = [contract.index(block) for block in expected_blocks]
        self.assertEqual(positions, sorted(positions))
        self.assertLessEqual(len(re.findall(r"\b[\w’-]+\b", contract)), 150)
        self.assertIn('<meta name="color-scheme" content="light">', base)

        portal_layout = source(TEMPLATES_DIR / "portal" / "layout.html")
        self.assertNotIn('<meta name="color-scheme"', portal_layout)

    def test_tables_cards_and_pagination_have_one_shared_owner(self) -> None:
        shell = source(CSS_DIR / "components" / "shell.css")

        for marker in [
            ".ui-table-shell",
            ".ui-data-table th",
            ".ui-data-table td",
            ".ui-data-card",
            ".ui-list-pagination",
            ".ui-list-pagination__meta",
            ".ui-support-color",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, shell)

        table_templates = [
            TEMPLATES_DIR / "portal" / "staff" / "customers" / "list.html",
            TEMPLATES_DIR / "portal" / "staff" / "customers" / "detail.html",
            TEMPLATES_DIR / "portal" / "staff" / "access_requests" / "list.html",
            TEMPLATES_DIR / "portal" / "staff" / "order_projects_list.html",
            TEMPLATES_DIR / "portal" / "client" / "partials" / "checkout_uploads.html",
        ]
        for template in table_templates:
            with self.subTest(template=template.name):
                markup = source(template)
                self.assertNotIn('class="table', markup)
                self.assertNotIn("dui-table", markup)
                self.assertIn("ui-data-table", markup)

        pagination = source(TEMPLATES_DIR / "components" / "portal" / "pagination.html")
        self.assertIn("ui-list-pagination__meta", pagination)
        self.assertIn("hx-target", pagination)

    def test_shared_pagination_preserves_filters_and_htmx_contract(self) -> None:
        page_obj = Paginator(range(5), 2).get_page(2)
        request = RequestFactory().get("/portal/orders/")

        markup = render_to_string(
            "components/portal/pagination.html",
            {
                "page_obj": page_obj,
                "pagination_base_url": "/portal/orders/",
                "search_query": "Atelier noir",
                "active_status": "submitted",
                "htmx_target": "#orders-results",
            },
            request=request,
        )

        for page_number in (1, 3):
            expected_url = (
                f"/portal/orders/?q=Atelier%20noir&amp;status=submitted&amp;page={page_number}"
            )
            with self.subTest(page_number=page_number):
                self.assertIn(f'href="{expected_url}"', markup)
                self.assertIn(f'hx-get="{expected_url}"', markup)
        self.assertEqual(markup.count('hx-target="#orders-results"'), 2)
        self.assertEqual(markup.count('hx-swap="innerHTML"'), 2)
        self.assertEqual(markup.count('hx-indicator="#portal-htmx-indicator"'), 2)

    def test_prospect_menu_toggle_is_standalone_44px_with_portal_css_only(self) -> None:
        header = source(TEMPLATES_DIR / "components" / "nav" / "landing_header.html")
        portal_entry = source(CSS_DIR / "entries" / "portal-core.css")
        surface_config = source(CSS_DIR / "entries" / "tailwind.surface.config.js")

        toggle = re.search(
            r'<button\s+type="button"\s+class="[^"]*product-menu-button[^"]*"',
            header,
        )
        self.assertIsNotNone(toggle)

        self.assertIn("prospect-tunnel.css", portal_entry)
        self.assertIn('content: ["./templates/**/*.html"]', surface_config)
        self.assertIn("corePlugins: []", surface_config)
        shell = source(CSS_DIR / "components" / "shell.css")
        toggle_rule = shell.split(
            'html[data-theme="prenium"] :is(body.product-shell, body.ui-marketing-body) '
            ".ui-foundation-nav .product-menu-button {",
            1,
        )
        self.assertGreater(len(toggle_rule), 1)
        toggle_block = toggle_rule[1].split("}", 1)[0]
        self.assertIn("display: inline-flex", toggle_block)
        self.assertIn("data-product-menu-toggle", header)
        self.assertIn('aria-controls="landing-primary-nav"', header)
        self.assertIn(
            ":is(body.product-shell, body.ui-marketing-body) .ui-foundation-nav",
            shell,
        )

    def test_portal_navigation_keeps_permissions_urls_and_clear_hierarchy(self) -> None:
        header = source(TEMPLATES_DIR / "components" / "nav" / "portal_header.html")
        client = source(TEMPLATES_DIR / "components" / "nav" / "portal_client_navigation.html")
        staff = source(TEMPLATES_DIR / "components" / "nav" / "portal_staff_navigation.html")
        create = source(TEMPLATES_DIR / "components" / "nav" / "portal_client_create_menu.html")
        profile = source(TEMPLATES_DIR / "components" / "nav" / "portal_profile_menu.html")

        self.assertIn("ui-foundation-nav", header)
        self.assertIn("ui-nav-rail", header)
        self.assertNotIn("ui-nav-panel", header)
        self.assertIn("Votre espace", client)
        self.assertIn("Pilotage quotidien", staff)
        self.assertIn("Administration Atelier", staff)
        self.assertIn("Votre compte", header)
        self.assertIn("ui-nav-action", create)

        for permission_contract in [
            "perms.orders.view_order and perms.production.view_productionjob and "
            "perms.production.scan_productionjob",
            "perms.customers.view_customer",
            "perms.production.view_productionmachine",
            "perms.prospects.view_prospectprofile",
            "perms.b2b_order_projects.view_b2borderproject",
            "perms.notifications.view_emailtemplate",
            "perms.customers.manage_customer_pricing",
            "perms.gang_sheets.configure_gangsheet",
            "perms.pod.access_pod_atelier",
        ]:
            with self.subTest(permission_contract=permission_contract):
                self.assertIn(permission_contract, staff)

        self.assertNotIn("perms.branding.view_brandthemesettings", staff)

        self.assertIn("portal_nav_access.customer_public_id", client)
        self.assertIn("portal_nav_access.project_creation_enabled", client)
        self.assertIn("portal_nav_access.project_creation_enabled", create)
        self.assertIn("portal_nav_access.can_manage_team", profile)
        self.assertIn("request.user.is_staff and perms.accounts.access_staff_portal", profile)
        self.assertIn('aria-current="page"', client)
        self.assertIn('aria-current="page"', staff)

    def test_staff_and_client_breadcrumb_trails_are_shared(self) -> None:
        page_head = source(TEMPLATES_DIR / "components/portal/page_head.html")
        staff_trail = source(TEMPLATES_DIR / "components/portal/breadcrumbs/staff_trail.html")
        client_trail = source(TEMPLATES_DIR / "components/portal/breadcrumbs/client_trail.html")

        self.assertIn('class="portal-page-rail"', page_head)
        self.assertLess(
            page_head.index('class="portal-page-rail"'),
            page_head.index("portal-page-intro"),
        )

        for marker in [
            'aria-label="Fil d’Ariane"',
            'class="ui-breadcrumb__list"',
            "Accueil Atelier",
            "portal:staff-dashboard",
        ]:
            with self.subTest(marker=marker, trail="staff"):
                self.assertIn(marker, staff_trail)

        for marker in [
            "Accueil",
            "portal:client-dashboard",
        ]:
            with self.subTest(marker=marker, trail="client"):
                self.assertIn(marker, client_trail)

        staff_wrappers = [
            "components/portal/breadcrumbs/staff_customers_list.html",
            "components/portal/breadcrumbs/staff_operations.html",
            "components/portal/breadcrumbs/staff_machines.html",
            "components/portal/breadcrumbs/staff_branding.html",
        ]
        for relative_path in staff_wrappers:
            with self.subTest(relative_path=relative_path):
                wrapper = source(TEMPLATES_DIR / relative_path)
                self.assertIn("staff_trail.html", wrapper)

        for relative_path, breadcrumb_partial in [
            ("portal/staff/customers/list.html", "staff_customers_list.html"),
            ("portal/staff/dashboard.html", "staff_atelier_home.html"),
            ("portal/staff/operations/index.html", "staff_operations.html"),
            ("portal/profile.html", "client_profile.html"),
        ]:
            with self.subTest(relative_path=relative_path):
                markup = source(TEMPLATES_DIR / relative_path)
                self.assertIn(breadcrumb_partial, markup)
