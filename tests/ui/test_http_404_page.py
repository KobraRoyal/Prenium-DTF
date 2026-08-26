from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "backend" / "templates"
User = get_user_model()


class Http404PageTests(TestCase):
    def test_404_template_uses_operate_auth_shell(self) -> None:
        html = (TEMPLATES_DIR / "404.html").read_text(encoding="utf-8")
        for marker in [
            "product-shell--auth product-shell--error",
            "product-error-card",
            "Page introuvable",
            "auth_header.html",
            "auth_support.html",
            "ui-btn-primary",
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, html)
        self.assertNotIn("dui-alert", html)
        self.assertNotIn("shadow-lg", html)

    @override_settings(DEBUG=False)
    def test_unknown_path_renders_custom_404_for_anonymous(self) -> None:
        client = Client()
        response = client.get("/chemin-introuvable-recette-404/")
        self.assertEqual(response.status_code, 404)
        body = response.content.decode("utf-8")
        self.assertIn("Page introuvable", body)
        self.assertIn("product-error-card", body)
        self.assertIn("Retour à l’accueil", body)
        self.assertIn(reverse("portal:login"), body)
        self.assertNotIn("Page not found at", body)

    @override_settings(DEBUG=False)
    def test_unknown_path_renders_workspace_cta_for_authenticated_user(self) -> None:
        user = User.objects.create_user(
            email="client.404@prenium.local",
            password="pass1234",
        )
        client = Client()
        client.force_login(user)
        response = client.get("/chemin-introuvable-recette-404/")
        self.assertEqual(response.status_code, 404)
        body = response.content.decode("utf-8")
        self.assertIn("Retour à mon espace", body)
        self.assertIn(reverse("portal:client-dashboard"), body)
        self.assertIn(reverse("home"), body)
