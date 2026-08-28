import json
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
CSS_DIR = BACKEND_DIR / "static_src" / "css"
TEMPLATES_DIR = BACKEND_DIR / "templates"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_css_entrypoints_keep_shared_and_surface_rules_separate() -> None:
    app_entry = read(CSS_DIR / "input.css")
    marketing_entry = read(CSS_DIR / "entries" / "marketing.css")
    portal_entry = read(CSS_DIR / "entries" / "portal.css")
    portal_core_entry = read(CSS_DIR / "entries" / "portal-core.css")
    studio_entry = read(CSS_DIR / "entries" / "studio.css")

    for common_import in [
        '"./tokens.css"',
        '"./legacy/app-legacy.css"',
        '"./components/shell.css"',
        '"./components/feedback.css"',
        '"./components/forms.css"',
        '"./components/buttons.css"',
    ]:
        assert common_import in app_entry

    for surface_component in [
        "product-shell.css",
        "landing.css",
        "prospect-journey.css",
        "gang-sheet-studio.css",
    ]:
        assert surface_component not in app_entry

    assert "landing.css" in marketing_entry
    assert "landing-conversion.css" in marketing_entry
    assert '@import "./portal-core.css"' in portal_entry
    assert '@import "./portal-client.css"' in portal_entry
    assert '@import "./portal-staff.css"' in portal_entry
    assert "workflow.css" in portal_core_entry
    assert "product-shell.css" in portal_core_entry
    assert "prospect-tunnel.css" in portal_core_entry
    assert "prospect-journey.css" in portal_entry
    assert "gang-sheet.css" in read(CSS_DIR / "entries" / "portal-client.css")
    assert "gang-sheet-studio.css" in studio_entry


def test_templates_load_common_css_before_exact_surface_bundle() -> None:
    base = read(TEMPLATES_DIR / "base.html")
    portal = read(TEMPLATES_DIR / "portal" / "layout.html")
    surface_styles = read(TEMPLATES_DIR / "components" / "portal" / "surface_styles.html")
    prospect = read(TEMPLATES_DIR / "prospects" / "base_tunnel.html")
    home = read(TEMPLATES_DIR / "shop" / "home.html")
    services = read(TEMPLATES_DIR / "shop" / "services.html")

    assert base.index("css/app.css") < base.index("{% block surface_styles %}")
    assert "surface_styles.html" in base
    assert "surface_styles.html" in portal
    assert "portal:client-gang-sheet-editor" in portal
    assert "css/studio.css" in portal
    assert "css/portal-core.css" in surface_styles
    assert "css/portal-staff.css" in surface_styles
    assert "css/portal-client.css" in surface_styles
    assert "surface_styles.html" in prospect
    assert "css/marketing.css" in home
    assert "css/portal-core.css" not in home
    assert "css/marketing.css" in services
    assert "css/portal-core.css" not in services


def test_generated_surface_bundles_exist_and_contain_expected_markers() -> None:
    bundles = {
        "app.css": [".ui-skip-link", ".ui-field-group"],
        "marketing.css": [".landing-reveal", ".conversion-hero"],
        "portal.css": [
            ".product-layout",
            ".workflow-next-action",
            ".gang-sheet-page",
            "body.product-shell",
            "--product-bg:var(--bg)",
            "tr.ui-row-warning",
        ],
        "portal-core.css": [
            ".portal-page-surface",
            "body.product-shell",
            "--product-bg:var(--bg)",
        ],
        "studio.css": [".gang-editor", ".gang-editor__workspace"],
    }

    for filename, markers in bundles.items():
        source = read(CSS_DIR / filename)
        assert source
        for marker in markers:
            assert marker in source

    assert ".conversion-hero" not in read(CSS_DIR / "app.css")
    assert "--gang-text-meta" not in read(CSS_DIR / "portal.css")
    assert "--gang-text-meta" in read(CSS_DIR / "studio.css")
    for surface_bundle in ["marketing.css", "portal.css", "portal-core.css", "studio.css"]:
        assert ".pointer-events-none{" not in read(CSS_DIR / surface_bundle)


def test_build_pipeline_and_runtime_image_ship_every_css_bundle() -> None:
    scripts = json.loads(read(BACKEND_DIR / "package.json"))["scripts"]
    dockerfile = read(ROOT_DIR / "infra" / "docker" / "backend" / "Dockerfile")

    for surface in ["app", "marketing", "portal", "studio"]:
        assert f"build:css:{surface}" in scripts
        assert f"static_src/css/{surface}.css" in dockerfile

    assert "npm run build:css:app" in scripts["build:css"]
    assert "npm run build:css:studio" in scripts["build:css"]
    assert "COPY backend/templates ./templates" in dockerfile
    assert dockerfile.index("COPY backend/templates ./templates") < dockerfile.index(
        "RUN npm run build:assets"
    )
    assert 'content: ["./templates/**/*.html"]' in read(
        CSS_DIR / "entries" / "tailwind.surface.config.js"
    )


def test_product_shell_keeps_shared_light_background_outside_tailwind_layer() -> None:
    source = read(CSS_DIR / "entries" / "portal-core.css")
    unlayered = source.split("@tailwind", 1)[0]

    assert "body.product-shell" in unlayered
    assert "background: var(--bg)" in unlayered


def test_shell_css_exposes_portal_page_breadcrumb_rail() -> None:
    portal_entry = read(CSS_DIR / "entries" / "portal-core.css")

    for marker in [
        ".portal-page-rail",
        ".portal-page--client",
        ".portal-page-intro",
        ".portal-page-surface",
        "main.app-main",
        "background: transparent !important",
        ".product-nav__links .ui-btn",
        "border: 0 !important",
    ]:
        assert marker in portal_entry


def test_built_portal_css_overrides_app_legacy_portal_shell() -> None:
    portal_css = read(CSS_DIR / "portal.css")

    for marker in [
        "portal-page-rail",
        "portal-page-intro",
        "portal-page-surface",
        "body.landing-saas.portal-shell.product-shell",
        "box-shadow:none!important",
        ".ui-btn-ghost",
        "filter:none!important",
        ".gang-sheet-card__facts",
    ]:
        assert marker.replace(" ", "") in portal_css.replace(" ", "")


def test_built_portal_core_skips_bem_focus_children() -> None:
    built = read(CSS_DIR / "portal-core.css").replace(" ", "")
    assert "[class*=-focus]:not([class*=__])" in built
    assert "[class*=-focus],.workflow-shell" not in built


def test_surface_templates_share_css_cache_bust_version() -> None:
    from apps.portal.templatetags.portal_tags import PORTAL_CSS_ASSET_V

    expected = PORTAL_CSS_ASSET_V
    surface_styles = read(TEMPLATES_DIR / "components" / "portal" / "surface_styles.html")
    layout = read(TEMPLATES_DIR / "portal" / "layout.html")

    assert "portal_css_asset_v" in surface_styles
    assert "?v={{ asset_v }}" in surface_styles
    assert "portal_css_asset_v" in layout
    assert expected == "20260828-studio-groups-v41"

    for path in (
        TEMPLATES_DIR / "portal" / "layout.html",
        TEMPLATES_DIR / "prospects" / "base_tunnel.html",
    ):
        source = read(path)
        assert "surface_styles.html" in source, path.name


def test_client_order_panels_avoid_legacy_panel_wrapper() -> None:
    for path in (
        "portal/client/panels/billing.html",
        "portal/client/panels/uploads.html",
        "portal/client/panels/production.html",
        "portal/client/panels/shipping.html",
        "portal/client/panels/inspection.html",
    ):
        source = read(TEMPLATES_DIR / path)
        assert 'class="panel ' not in source, path
        assert "client-order-panel" in source, path


def test_client_order_inspection_uses_ui_kpi_cards() -> None:
    source = read(TEMPLATES_DIR / "portal/client/panels/inspection.html")
    kpi_partial = read(TEMPLATES_DIR / "components/tables/kpi_grid.html")
    assert "ui_kpi_grid" in source
    assert "ui-kpi-grid" in kpi_partial
    assert 'article class="card"' not in source
    assert "panel-head" not in source


def test_b2b_partials_avoid_legacy_card_wrapper() -> None:
    for path in (
        "portal/client/partials/order_project_items.html",
        "portal/client/partials/order_project_fields.html",
    ):
        source = read(TEMPLATES_DIR / path)
        assert 'class="card b2b-' not in source, path


def test_client_checkout_avoids_nested_product_panel_surface() -> None:
    source = read(TEMPLATES_DIR / "portal/client/checkout.html")
    assert "client-checkout-intro" in source
    assert "product-panel" not in source


def test_portal_core_portal_shell_disables_brutalist_shadows() -> None:
    source = read(CSS_DIR / "entries" / "portal-core.css")
    assert "v29 — Shell portail clair" in source
    assert "prefers-reduced-motion" in source


def test_portal_core_guards_bem_elements_from_attribute_card_selectors() -> None:
    source = read(CSS_DIR / "entries" / "portal-core.css")

    assert '[class*="-card"]:not([class*="__"])' in source
    assert '[class*="-row"]:not([class*="__"])' in source
    assert ".portal-page-surface .empty-state" in source
    assert ".portal-page-surface .workflow-panel" in source
    assert ".portal-page-surface .client-order-summary" in source
    assert ".portal-page-surface .workflow-tab-rail" in source
    assert "--portal-inner-chrome: empty" in source


def test_staff_focus_templates_avoid_legacy_card_wrapper() -> None:
    for path in (
        "portal/staff/order_detail.html",
        "portal/staff/order_project_detail.html",
        "portal/staff/customers/detail.html",
        "portal/staff/access_requests/detail.html",
    ):
        source = read(TEMPLATES_DIR / path)
        assert 'class="card staff-' not in source, path
