import ast
from pathlib import Path

import pytest
from django.urls import resolve, reverse


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _portal_module_path(module_name: str) -> Path:
    return _repo_root() / "backend" / "apps" / "portal" / f"{module_name}.py"


def _portal_imports(module_name: str) -> set[str]:
    module_path = _portal_module_path(module_name)
    tree = ast.parse(module_path.read_text(), filename=str(module_path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                parts = module_name.split(".")[: -node.level]
                module = ".".join(parts + [node.module]) if parts else node.module
                imports.add(module)
            else:
                imports.add(node.module)
    return imports


def _module_line_count(module_name: str) -> int:
    return len(_portal_module_path(module_name).read_text().splitlines())


def test_portal_legacy_views_facade_is_removed():
    legacy_module = _repo_root() / "backend" / "apps" / "portal" / "views.py"
    assert not legacy_module.exists()


@pytest.mark.parametrize(
    ("route_name", "kwargs", "expected_module"),
    [
        ("portal:login", {}, "apps.portal.views_auth"),
        ("portal:profile", {}, "apps.portal.views_profile"),
        ("portal:client-dashboard", {}, "apps.portal.views_client"),
        (
            "portal:client-checkout",
            {"customer_public_id": "00000000-0000-0000-0000-000000000001"},
            "apps.portal.views_checkout",
        ),
        ("portal:staff-dashboard", {}, "apps.portal.views_staff_dashboard"),
        (
            "portal:staff-manufacturing-order-batch-pdf",
            {},
            "apps.portal.views_staff_documents",
        ),
        (
            "portal:staff-order-panel-uploads",
            {"order_public_id": "00000000-0000-0000-0000-000000000001"},
            "apps.portal.views_staff_uploads",
        ),
        (
            "portal:staff-order-panel-inspection",
            {"order_public_id": "00000000-0000-0000-0000-000000000001"},
            "apps.portal.views_staff_reviews",
        ),
        (
            "portal:staff-order-panel-production",
            {"order_public_id": "00000000-0000-0000-0000-000000000001"},
            "apps.portal.views_staff_production",
        ),
        (
            "portal:staff-order-panel-shipping",
            {"order_public_id": "00000000-0000-0000-0000-000000000001"},
            "apps.portal.views_staff_shipping",
        ),
        (
            "portal:staff-order-panel-billing",
            {"order_public_id": "00000000-0000-0000-0000-000000000001"},
            "apps.portal.views_staff_billing",
        ),
    ],
)
def test_portal_routes_resolve_to_specialized_modules(route_name, kwargs, expected_module):
    match = resolve(reverse(route_name, kwargs=kwargs))
    assert match.func.view_class.__module__ == expected_module


@pytest.mark.parametrize(
    ("module_name", "allowed_internal_imports"),
    [
        ("views_auth", {"apps.portal.views_common"}),
        ("views_profile", {"apps.portal.views_common"}),
        ("views_client", {"apps.portal.views_common"}),
        ("views_checkout", {"apps.portal.htmx", "apps.portal.views_common"}),
        ("views_staff", {"apps.portal.views_common"}),
        ("views_staff_dashboard", {"apps.portal.views_common"}),
        ("views_staff_documents", {"apps.portal.views_common"}),
        (
            "views_staff_uploads",
            {"apps.portal.views_common", "apps.portal.views_staff"},
        ),
        (
            "views_staff_reviews",
            {"apps.portal.htmx", "apps.portal.views_common", "apps.portal.views_staff"},
        ),
        (
            "views_staff_production",
            {"apps.portal.htmx", "apps.portal.views_common", "apps.portal.views_staff"},
        ),
        (
            "views_staff_shipping",
            {"apps.portal.htmx", "apps.portal.views_common", "apps.portal.views_staff"},
        ),
        (
            "views_staff_billing",
            {"apps.portal.htmx", "apps.portal.views_common", "apps.portal.views_staff"},
        ),
    ],
)
def test_portal_modules_keep_expected_internal_import_boundaries(
    module_name, allowed_internal_imports
):
    portal_imports = {
        item for item in _portal_imports(module_name) if item.startswith("apps.portal.")
    }
    assert "apps.portal.views" not in portal_imports
    assert portal_imports <= allowed_internal_imports


@pytest.mark.parametrize(
    ("module_name", "max_lines"),
    [
        ("views_auth", 60),
        ("views_profile", 90),
        ("views_staff_uploads", 130),
        ("views_staff_reviews", 170),
        ("views_staff", 180),
        ("views_staff_dashboard", 90),
        ("views_staff_documents", 70),
        ("views_staff_billing", 170),
        ("views_staff_production", 180),
        ("views_staff_shipping", 190),
        ("views_common", 220),
        ("views_checkout", 260),
        ("views_client", 400),
    ],
)
def test_portal_modules_stay_within_expected_size_limits(module_name, max_lines):
    assert _module_line_count(module_name) <= max_lines
