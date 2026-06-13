# prenium-dtf.com via IDS supply

Application Django monolithique modulaire pour le SaaS e-commerce premium DTF, exécutée sous Docker Compose.

Le dépôt contient :
- l'application backend Django ;
- le portail client et staff en Django templates / HTMX / Alpine ;
- l'infrastructure Docker / Nginx / PostgreSQL / Redis / Celery ;
- la documentation produit, architecture, sécurité et sprints.

## Services Docker

Services actuellement utilisés via `docker-compose.yml` :

- `db` : PostgreSQL 16
- `redis` : cache Django et broker / backend Celery
- `web` : Django + Gunicorn
- `worker` : Celery worker
- `nginx` : reverse proxy HTTP et statiques

Il n'existe pas de service `frontend` dédié. Le CSS est construit dans la chaîne Docker du backend.

## Structure du dépôt

- `backend/` : application Django, templates, assets Tailwind/DaisyUI, requirements
- `docs/` : sprints, architecture, sécurité, suivi produit
- `infra/` : Dockerfiles, entrypoints, notes d'exploitation
- `tests/` : tests organisés par domaine fonctionnel et UI
- `docker-compose.yml` : pile locale / dev
- `docker-compose.prod.yml` : variante runtime prod-like
- `AGENTS.md` : règles d'exécution projet pour Codex

## Backend

Le backend est déjà en place, avec apps métier séparées :

- `accounts`
- `auditlog`
- `billing`
- `catalog`
- `core`
- `customers`
- `notifications`
- `orders`
- `portal`
- `production`
- `prospects`
- `shipping`
- `shipping_sendcloud`
- `uploads`

Configuration Django :
- `backend/config/settings/`

Assets UI :
- `backend/static_src/`
- `backend/templates/`

## Démarrage local

Démarrer la pile :

```bash
docker compose up -d db redis web worker nginx
```

Healthcheck :

```bash
curl --fail --silent --show-error http://localhost:8080/healthz/
```

Connexion portail :

- [http://localhost:8080/login/](http://localhost:8080/login/)

## Vérifications usuelles

Raccourcis disponibles :

```bash
make up
make health
make check
make migrations-plan
make test
make test-ui
make test-orders
make lint
make format
make audit
make shell
make logs-web
make logs-worker
```

Contrôle Django :

```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
docker compose exec web sh -lc 'cd /app/backend && python manage.py makemigrations --check --dry-run'
```

Tests et qualité :

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'
```

## Ordre de lecture recommandé

1. `AGENTS.md`
2. `docs/sprints/SPRINTS_INDEX.md`
3. `docs/security/SECURITY_BASELINE.md`
4. `docs/tracking/PROJECT_STATUS.md`
5. `infra/README.md`

## Règles de travail

- privilégier les changements petits et testés ;
- valider sous Docker ;
- ne pas mélanger refactoring structurel et changement métier sensible ;
- mettre à jour la documentation du lot concerné ;
- conserver l'isolation stricte des données client.
