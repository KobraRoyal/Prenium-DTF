from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse


class HttpErrorPagesTests(TestCase):
    def test_error_templates_share_auth_operate_shell(self) -> None:
        templates = Path(settings.BASE_DIR) / "templates"
        page_404 = (templates / "404.html").read_text(encoding="utf-8")
        page_500 = (templates / "500.html").read_text(encoding="utf-8")

        for source in (page_404, page_500):
            self.assertIn("product-shell--error", source)
            self.assertIn("product-error-card", source)
            self.assertIn("product-error-card__code", source)
            self.assertIn("auth_header.html", source)
            self.assertIn("auth_support.html", source)

        self.assertIn("Page introuvable", page_404)
        self.assertIn(">404<", page_404)
        self.assertIn("Une erreur est survenue", page_500)
        self.assertIn(">500<", page_500)

    @override_settings(DEBUG=False, SETTINGS_MODULE="config.settings.dev")
    def test_dev_preview_routes_render_custom_error_pages(self) -> None:
        response_404 = self.client.get(reverse("http-error-preview-404"))
        response_500 = self.client.get(reverse("http-error-preview-500"))

        self.assertEqual(response_404.status_code, 404)
        self.assertContains(response_404, "Page introuvable", status_code=404)
        self.assertContains(response_404, "product-error-card__code", status_code=404)

        self.assertEqual(response_500.status_code, 500)
        self.assertContains(response_500, "Une erreur est survenue", status_code=500)
        self.assertContains(response_500, "product-error-card__code", status_code=500)

    @override_settings(DEBUG=False)
    def test_unknown_url_uses_custom_404_when_debug_off(self) -> None:
        response = self.client.get("/cette-page-n-existe-vraiment-pas-404/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page introuvable", status_code=404)
        self.assertContains(response, "product-error-card", status_code=404)
