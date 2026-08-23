"""Contrat UI homogène — vues portail client et Atelier (page par page)."""

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES_DIR = Path(settings.BASE_DIR) / "templates"

CLIENT_PAGE_VIEWS = [
    "portal/client/dashboard.html",
    "portal/client/checkout.html",
    "portal/client/orders_list.html",
    "portal/client/order_detail.html",
    "portal/client/order_projects_list.html",
    "portal/client/order_project_detail.html",
    "portal/client/order_project_form.html",
    "portal/client/gang_sheets/create_order_project.html",
    "portal/client/gang_sheets/list.html",
    "portal/client/team.html",
    "portal/profile.html",
]

STAFF_PAGE_VIEWS = [
    "portal/staff/dashboard.html",
    "portal/staff/operations/index.html",
    "portal/staff/orders_list.html",
    "portal/staff/order_projects_list.html",
    "portal/staff/customers/list.html",
    "portal/staff/access_requests/list.html",
    "portal/staff/machines/index.html",
    "portal/staff/email_templates/list.html",
    "portal/staff/email_templates/edit.html",
    "portal/staff/settings/branding.html",
    "portal/staff/gang_sheets/settings.html",
    "portal/staff/customers/default_volume_discounts.html",
]

STAFF_FOCUS_VIEWS = [
    "portal/staff/order_detail.html",
    "portal/staff/order_project_detail.html",
    "portal/staff/customers/detail.html",
    "portal/staff/access_requests/detail.html",
]

LEGACY_PATTERNS = [
    (r'class="btn"', "class=\"btn\""),
    ("product-eyebrow", "product-eyebrow"),
    ("agency-", "agency-"),
    (r'\bopacity-\d+\b', "opacity-* utility"),
]

RAW_EMPTY_STATE = re.compile(
    r'<div[^>]*class="[^"]*\bempty-state\b[^"]*"[^>]*>',
    re.IGNORECASE,
)

EMPTY_STATE_EXCEPTIONS = {
    "portal/client/gang_sheets/list.html": "Alpine filtered empty (x-show)",
}


def template_source(relative_path: str) -> str:
    return (TEMPLATES_DIR / relative_path).read_text(encoding="utf-8")


class PortalViewsUiHomogeneityTests(SimpleTestCase):
    def test_client_pages_use_portal_page_client_shell(self) -> None:
        surface_optional = {
            "portal/client/dashboard.html",
            "portal/client/order_detail.html",
            "portal/client/order_project_detail.html",
        }
        for path in CLIENT_PAGE_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('extends "portal/layout.html"', source)
                self.assertIn("portal-page--client", source)
                self.assertIn("page_head.html", source)
                if path not in surface_optional:
                    self.assertIn("portal-page-surface", source)

    def test_staff_list_pages_use_portal_page_staff_shell(self) -> None:
        for path in STAFF_PAGE_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn('extends "portal/layout.html"', source)
                self.assertIn("portal-page--staff", source)
                self.assertIn("page_head.html", source)

    def test_staff_focus_pages_use_portal_page_staff_without_page_head(self) -> None:
        focus_markers = (
            "staff-order-focus",
            "staff-project-focus",
            "staff-customer-focus",
            "staff-access-focus",
        )
        for path in STAFF_FOCUS_VIEWS:
            with self.subTest(path=path):
                source = template_source(path)
                self.assertIn("portal-page--staff", source)
                self.assertNotIn("page_head.html", source)
                self.assertTrue(any(marker in source for marker in focus_markers))

    def test_portal_page_titles_use_em_dash_brand_suffix(self) -> None:
        all_views = CLIENT_PAGE_VIEWS + STAFF_PAGE_VIEWS + STAFF_FOCUS_VIEWS
        for path in all_views:
            with self.subTest(path=path):
                source = template_source(path)
                match = re.search(r"{% block title %}(.*?){% endblock %}", source, re.DOTALL)
                self.assertIsNotNone(match, f"{path} : block title manquant")
                title = match.group(1).strip()
                self.assertIn("— Prenium DTF", title, f"{path} : titre sans suffixe marque")

    def test_portal_pages_avoid_legacy_visual_patterns(self) -> None:
        all_views = CLIENT_PAGE_VIEWS + STAFF_PAGE_VIEWS + STAFF_FOCUS_VIEWS
        for path in all_views:
            with self.subTest(path=path):
                source = template_source(path)
                for pattern, label in LEGACY_PATTERNS:
                    self.assertIsNone(re.search(pattern, source), f"{path} : reliquat {label}")

    def test_portal_pages_prefer_shared_empty_state_partial(self) -> None:
        all_views = CLIENT_PAGE_VIEWS + STAFF_PAGE_VIEWS + STAFF_FOCUS_VIEWS
        for path in all_views:
            if path in EMPTY_STATE_EXCEPTIONS:
                continue
            with self.subTest(path=path):
                source = template_source(path)
                for match in RAW_EMPTY_STATE.finditer(source):
                    snippet = source[max(0, match.start() - 40) : match.end() + 80]
                    if "empty_state.html" in snippet:
                        continue
                    if "x-show" in snippet or "x-cloak" in snippet:
                        continue
                    self.fail(f"{path} : empty-state brut sans partial partagé : {match.group(0)!r}")

    def test_empty_state_partial_supports_dialog_open_cta(self) -> None:
        source = template_source("components/ui/empty_state.html")
        self.assertIn("cta_button_dialog_open", source)
        self.assertIn("data-dialog-open", source)

    def test_staff_css_mirrors_client_page_head_homogeneity(self) -> None:
        css = (Path(settings.BASE_DIR) / "static_src/css/entries/portal-core.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".portal-page--staff .portal-page-intro", css)
        self.assertIn(".portal-page--client .portal-page-intro", css)
