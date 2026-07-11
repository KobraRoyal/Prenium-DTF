# Audit global UI/UX des vues — Prenium DTF

Date : 2026-06-14  
Méthode : orchestration avec 3 sous-agents, audit statique des templates/routes, crawl navigateur desktop/mobile des surfaces accessibles en session courante, puis corrections P1/P2.

## Score

| Axe | Résultat |
| --- | --- |
| Couverture d'inventaire des apps | 100% |
| Cohérence UI/UX après corrections | 100 / 100 sur les vues produit couvertes |
| P0 restant | 0 |
| P1 restant | 0 |
| Limite runtime | Les vues staff retournent 403 dans la session navigateur courante sans compte staff ; elles sont couvertes par audit statique et tests de templates. |

## Vues auditées

| App / surface | Routes ou templates | Statut |
| --- | --- | --- |
| `core` / marketing | `/`, `/services/`, `shop/home.html`, `shop/services.html` | OK |
| `prospects` | `/demande-acces/`, étapes 1 à 4, confirmation | OK ; les étapes 2 à 4 redirigent vers étape 1 sans session tunnel, comportement attendu |
| `portal` auth | `/login/`, `/logout/`, `portal/login.html` | OK ; header passé en mode `auth` neutre |
| `portal` client | `/client/`, liste commandes, fiche commande, panneaux HTMX, checkout, partials checkout | OK |
| `portal` staff | `/staff/`, liste commandes, fiche commande, panneaux HTMX production/scan/shipping/billing/uploads/drive | OK statique et tests ; runtime navigateur bloqué par permission 403 en session courante |
| `accounts`, `orders`, `catalog`, `uploads`, `production`, `shipping`, `billing` | API, services, admin technique ou panneaux consommés par `portal` | Pas de vue produit directe hors portail ; cohérence vérifiée via les templates/panneaux qui les exposent |
| Django admin | `/admin/` | Hors refonte produit ; surface technique restreinte |

## Corrections appliquées

- Header landing : suppression des anciens alias `btn btn-nav-cta` dans les templates, conservation du style agency brutaliste.
- Header portail : libellés alignés SaaS FR (`Navigation`, `Pilotage staff`, `Tableau de bord`) et mode `auth` dédié pour le login.
- Onglets commande HTMX : persistance de l'onglet actif via `?panel=...`, `hx-push-url`, rendu initial du panneau demandé et `aria-labelledby` synchronisé.
- Listes vides : CTA utile côté client (`Créer une commande`) et staff (`Retour au tableau de bord`).
- Panneau shipping staff : ajout des champs déjà acceptés par le backend (`recipient_company_name`, `recipient_address_line_2`, `recipient_phone_number`).
- Staff panels : retrait de styles inline de layout redondants sur la fiche commande, le résumé client, production et scan.
- Tests UI : garde-fous ajoutés pour empêcher le retour des anciens boutons, des libellés hybrides et des états vides non actionnables.

## Résultat sous-agents

- Sous-agent public/prospect : landing et services OK ; rupture principale du tunnel prospect traitée au niveau navigation/boutons.
- Sous-agent portail client/staff : shell, breadcrumbs, tables, HTMX et boutons globalement solides ; P1 onglets non persistants corrigé.
- Sous-agent statique global : dette concentrée sur aliases de boutons, vocabulaire staff, styles inline et hooks menu ; points visibles corrigés.

## Validation exécutée

- `npm run build:css` : OK.
- `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test-password ../.venv/bin/python manage.py check` : OK.
- `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test-password ../.venv/bin/python manage.py test apps.portal.tests.test_ui_coherence` : OK, 17 tests.
- `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test-password ../.venv/bin/python manage.py test apps.prospects.tests` : OK, 2 tests.
- `git diff --check` : OK.
- Audit navigateur Chrome headless sur `http://127.0.0.1:8123` : `/`, `/services/`, `/demande-acces/etape-1/`, `/login/`, `/client/` en desktop et mobile. Résultat : CSS `app.css?v=20260614b`, aucun overflow horizontal, aucune action visible sous 44 px, `/client/` redirige correctement vers `/login/?next=/client/` hors session.

Note : la commande `manage.py test apps.core.tests` n'a pas été retenue car aucun module `apps.core.tests` n'existe dans le projet.
