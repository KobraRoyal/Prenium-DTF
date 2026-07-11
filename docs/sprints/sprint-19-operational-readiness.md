# Sprint 19 — Operational readiness

Date : 2026-07-10

## Objectif

Fermer les écarts P1 de l’audit global : CI complète, tâches périodiques réellement exécutées,
emails asynchrones, configuration de production documentée et dépendances frontend autonomes.

## Livré

- découverte Pytest étendue à `tests/` et `backend/apps/` ;
- baseline Ruff alignée sur Python 3.12 ;
- service Celery Beat ajouté aux Compose local et production ;
- polling Sendcloud planifié depuis les settings communs ;
- concurrence worker limitée à 2 par défaut pour le NAS ;
- emails transactionnels déplacés vers quatre tâches Celery avec cinq retries et backoff ;
- SMTP, PayPal, expéditeur Sendcloud, HSTS et paramètres Celery documentés dans `.env.example` ;
- HTMX et Alpine.js auto-hébergés depuis des versions npm verrouillées ;
- PostCSS mis à jour et audits npm/Python sans vulnérabilité connue ;
- contexte Docker allégé des caches, dépendances locales et documents non nécessaires au runtime.

## Validation automatisée

- [x] `ruff check .`
- [x] `ruff format --check .`
- [x] `pytest` Python 3.12 : 261 tests passés
- [x] `manage.py check`
- [x] `makemigrations --check --dry-run`
- [x] `pip-audit -r backend/requirements/prod.txt`
- [x] `npm audit --audit-level=moderate`
- [x] `docker compose config --quiet` local et production
- [x] build local et production Docker
- [x] smoke runtime Docker : six services healthy, HTTP, worker, Beat et statiques vendor
- [x] `manage.py check --deploy` avec configuration production sécurisée
- [x] smoke navigateur desktop/mobile : landing, menu 375 px, services et login sans erreur console

## Recette environnement cible

À exécuter avec les vraies valeurs de production, sans les committer :

1. renseigner SMTP, Sendcloud, PayPal, domaine HTTPS et secrets dans `.env` ;
2. démarrer `db redis web worker beat nginx` ;
3. vérifier `/healthz/`, les logs Beat et le ping worker ;
4. déclencher un email de recette et une synchronisation Sendcloud manuelle ;
5. vérifier sauvegarde PostgreSQL et médias selon `infra/README.md`.
