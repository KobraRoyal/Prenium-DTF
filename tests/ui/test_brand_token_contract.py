from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
CSS_DIR = BACKEND_DIR / "static_src" / "css"
TEMPLATES_DIR = BACKEND_DIR / "templates"

DEAD_BROWN = ("#8f3d1f", "#8F3D1F", "#6f2f17", "#6F2F17")
GENERATED_BUNDLES = {
    "app.css",
    "marketing.css",
    "portal.css",
    "portal-core.css",
    "portal-client.css",
    "portal-staff.css",
    "prospect.css",
    "studio.css",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _source_css_files() -> list[Path]:
    files = []
    for path in CSS_DIR.rglob("*.css"):
        if path.name in GENERATED_BUNDLES:
            continue
        files.append(path)
    return files


def test_source_css_does_not_hardcode_legacy_brown_brand() -> None:
    offenders = []
    for path in _source_css_files():
        text = _read(path)
        for hex_value in DEAD_BROWN:
            if hex_value in text:
                offenders.append(f"{path.relative_to(ROOT_DIR)}:{hex_value}")
    assert offenders == []


def test_tailwind_theme_follows_live_brand_tokens() -> None:
    config = _read(BACKEND_DIR / "tailwind.config.js")
    assert 'DEFAULT: "var(--brand)"' in config
    assert 'strong: "var(--brand-strong)"' in config
    assert 'primary: "#ff8775"' in config
    assert 'secondary: "#a83bc4"' in config
    assert "#8f3d1f" not in config


def test_tokens_expose_runtime_alias_and_action_derivation() -> None:
    tokens = _read(CSS_DIR / "tokens.css")
    assert "--brand: #ff8775" in tokens
    assert "--accent: #a83bc4" in tokens
    assert "--ui-brand: var(--brand)" in tokens
    assert "--ui-action-primary-bg: var(--brand)" in tokens
    assert "--ui-action-primary-bg-hover: var(--brand-strong)" in tokens


def test_html_injects_atelier_brand_overrides() -> None:
    base = _read(TEMPLATES_DIR / "base.html")
    for contract in [
        "--brand: {{ site_brand_theme.primary",
        "--brand-strong: {{ site_brand_theme.primary_strong",
        "--accent: {{ site_brand_theme.secondary",
        "--accent-strong: {{ site_brand_theme.secondary_strong",
        "--action-text: {{ site_brand_theme.primary_ink",
    ]:
        assert contract in base


def test_action_buttons_use_token_variables_not_hex() -> None:
    buttons = _read(CSS_DIR / "components" / "buttons.css")
    assert "background: var(--ui-action-primary-bg)" in buttons
    assert "#ff8775" not in buttons
    assert "#8f3d1f" not in buttons


def test_atelier_branding_view_is_the_dedicated_admin_surface() -> None:
    branding = _read(TEMPLATES_DIR / "portal" / "staff" / "settings" / "branding.html")
    assert "Identité visuelle" in branding
    assert "primary_color" in branding
    assert "secondary_color" in branding
    assert 'type="color"' in branding
    assert "brand-preview" in branding
