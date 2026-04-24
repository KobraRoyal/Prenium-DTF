# Sprint 00 — Fondations

## Objectif
Mettre en place le socle exécutable du projet.

## Livrables
- [x] repo structuré
- [x] Docker Compose
- [x] Django initial
- [x] PostgreSQL
- [x] Redis
- [x] Celery
- [x] CI minimale

## Tâches
- [x] créer arborescence backend / infra / tests
- [x] config Docker / Nginx / services runtime
- [x] settings séparés `base` / `dev` / `test` / `prod`
- [x] healthcheck HTTP + management command
- [x] pre-commit
- [x] linters / formatter
- [x] apps initiales `core`, `accounts`, `customers`, `auditlog`
- [x] base pytest + smoke tests
- [x] CI GitHub Actions minimale
- [x] stabilisation 00.1 sur statiques, auth email, scope client et CI PostgreSQL

## Tests
- [x] démarrage stack `docker compose up -d --build`
- [x] migration OK
- [x] worker OK
- [x] test simple CI OK
- [x] test PostgreSQL réel en CI configuré

## Notes d’implémentation
- UI initiale retenue : Django templates + HTMX + Alpine + Tailwind, sans UI métier avancée dans ce sprint.
- Les ressources exposables sont préparées avec `public_id` UUID non prédictible.
- L’accès fichier reste backend-only par défaut : aucun mapping média public n’a été exposé.
- L’audit est préparé par une app dédiée et un service minimal, sans branchement métier avancé à ce stade.
- Authentification figée sur email comme identifiant de connexion.
- `Customer` sert de compte client minimal et `CustomerMembership` prépare le multi-utilisateur sans figer encore le RBAC.
- Les statiques sont servis par Nginx via volume dédié, hors source tree.

## Validation réalisée
- `python backend/manage.py check --settings=config.settings.test`
- `pytest`
- `ruff check .`
- `ruff format --check .`
- `docker compose config`
- `docker compose up -d --build`
- `curl http://localhost:8080/healthz/`
