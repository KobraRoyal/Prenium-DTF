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
    assert "workflow.css" in portal_entry
    assert "product-shell.css" in portal_entry
    assert "client-dashboard.css" in portal_entry
    assert portal_entry.index("product-shell.css") < portal_entry.index("client-dashboard.css")
    assert "prospect-tunnel.css" in portal_entry
    assert "prospect-journey.css" in portal_entry
    assert "gang-sheet.css" in portal_entry
    assert "gang-sheet-studio.css" in studio_entry


def test_templates_load_common_css_before_exact_surface_bundle() -> None:
    base = read(TEMPLATES_DIR / "base.html")
    portal = read(TEMPLATES_DIR / "portal" / "layout.html")
    prospect = read(TEMPLATES_DIR / "prospects" / "base_tunnel.html")
    home = read(TEMPLATES_DIR / "shop" / "home.html")
    services = read(TEMPLATES_DIR / "shop" / "services.html")

    assert base.index("css/app.css") < base.index("{% block surface_styles %}")
    assert "css/portal.css" in base
    assert "css/portal.css" in portal
    assert "portal:client-gang-sheet-editor" in portal
    assert portal.index("css/portal.css") < portal.index("css/studio.css")
    assert "css/portal.css" in prospect
    assert "css/marketing.css" in home
    assert "css/portal.css" not in home
    assert "css/marketing.css" in services
    assert "css/portal.css" not in services


def test_generated_surface_bundles_exist_and_contain_expected_markers() -> None:
    bundles = {
        "app.css": [".ui-skip-link", ".ui-field-group"],
        "marketing.css": [".landing-reveal", ".conversion-hero"],
        "portal.css": [
            ".product-layout",
            ".workflow-next-action",
            ".gang-sheet-page",
            "body.product-shell",
            "#f7f5f0",
            ".client-dashboard-head",
            ".client-dashboard-board",
            ".client-dashboard-list__item",
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
    for surface_bundle in ["marketing.css", "portal.css", "studio.css"]:
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


def test_product_shell_beats_dark_landing_background_outside_tailwind_layer() -> None:
    source = read(CSS_DIR / "entries" / "portal.css")
    unlayered = source.split("@tailwind", 1)[0]

    assert "body.product-shell" in unlayered
    assert "background: #f7f5f0" in unlayered
