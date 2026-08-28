from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from json import loads
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    return (ROOT_DIR / relative_path).read_text(encoding="utf-8")


def _production_environment(*, static_root: str | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "DJANGO_SECRET_KEY": "static-assets-test-" + "a8F4zP9qK2mN7xR5" * 4,
            "DJANGO_ALLOWED_HOSTS": "example.com",
            "DJANGO_EMAIL_HOST": "smtp.example.com",
            "POSTGRES_PASSWORD": "test-only-password",
            "PYTHONPATH": str(ROOT_DIR / "backend"),
        }
    )
    if static_root is not None:
        environment["DJANGO_STATIC_ROOT"] = static_root
    return environment


def test_production_uses_content_hashed_static_assets() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from django.conf import settings; "
            "print(settings.STORAGES['staticfiles']['BACKEND']); "
            "print(settings.STORAGES['default']['BACKEND'])",
        ],
        cwd=ROOT_DIR,
        env=_production_environment(),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        "django.core.files.storage.FileSystemStorage",
    ]


def test_production_collectstatic_hashes_every_surface_bundle() -> None:
    with tempfile.TemporaryDirectory(prefix="prenium-static-manifest-") as static_root:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT_DIR / "backend" / "manage.py"),
                "collectstatic",
                "--noinput",
            ],
            cwd=ROOT_DIR,
            env=_production_environment(static_root=static_root),
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        manifest = loads((Path(static_root) / "staticfiles.json").read_text())
        for filename in ("app.css", "marketing.css", "portal.css", "studio.css"):
            source_name = f"css/{filename}"
            hashed_name = manifest["paths"][source_name]
            assert hashed_name != source_name
            assert (Path(static_root) / hashed_name).is_file()


def test_entrypoint_assets_do_not_depend_on_manual_query_versions() -> None:
    base = _source("backend/templates/base.html")
    home = _source("backend/templates/shop/home.html")
    services = _source("backend/templates/shop/services.html")

    assert "app.css' %}?v=" not in base
    # Entrypoint JS : cache-bust via tag portal (pas de version calendaire en dur).
    assert "js/app.js' %}?v={{ asset_v }}" in base
    assert "js/app.js' %}?v=20" not in base
    assert "marketing.js' %}?v=" not in home
    assert "marketing.js' %}?v=" not in services


def test_javascript_module_children_keep_explicit_cache_versions() -> None:
    # Django's stable manifest backend fingerprints entrypoints but does not yet
    # rewrite ES-module imports. Keep child imports versioned until a bundler or
    # a production-proven module-aware storage owns the complete dependency graph.
    app = _source("backend/static_src/js/app.js")
    assert "?v=" in app
    assert "gang-sheet-editor.js?v=20260828-studio-groups-v23" in app
    assert "?v=" in _source("backend/static_src/js/marketing.js")


def test_css_resolves_fonts_from_static_root() -> None:
    legacy_css = _source("backend/static_src/css/legacy/app-legacy.css")

    assert 'url("/static/vendor/fonts/dm-sans-latin-wght-normal.woff2")' in legacy_css
    assert 'url("/static/vendor/fonts/space-grotesk-latin-wght-normal.woff2")' in legacy_css


def test_vendored_pdfjs_does_not_reference_unshipped_source_maps() -> None:
    copy_script = _source("backend/scripts/copy-vendor.mjs")

    assert "copyPdfJsWithoutSourceMap" in copy_script
    for filename in ("pdf.js", "pdf.worker.js", "pdf.mjs", "pdf.worker.mjs"):
        assert "sourceMappingURL=" not in _source(f"backend/static_src/vendor/pdfjs/{filename}")
