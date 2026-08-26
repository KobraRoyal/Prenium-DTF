# Sprint 50 — Page HTTP 404 Operate

## Objectif
Livrer une page « Page introuvable » cohérente avec le shell auth Operate (pas de chrome brutaliste), utilisable anonymes et connectés.

## Livrables
- Template `backend/templates/404.html` (carte `product-error-card`, CTAs contextuels).
- Handler `handler404` dans `backend/config/urls.py` (`django.views.defaults.page_not_found`).
- Styles Operate dans `backend/static_src/css/components/auth-login.css`.
- Tests : `tests/ui/test_http_404_page.py` (DEBUG=False).

## Comportement
- Anonyme : CTA principal Accueil, secondaire Connexion.
- Authentifié : CTA principal « Retour à mon espace » (`brand_home_url` → client ou Atelier), secondaire Accueil.
- Support : partial `auth_support.html`.
- Visible en prod/recette avec `DEBUG=False` ; en `config.settings.dev`, `DJANGO_DEBUG` est lu depuis l’env (défaut `True`) — passer `False` pour prévisualiser la 404 Operate.

## Checklist
- [x] Template Operate (radius tokens, `ui-btn`, pas Daisy toast/alert)
- [x] Handler URLconf
- [x] Tests anonymous + authenticated
- [x] Doc recette + index sprints + statut projet
