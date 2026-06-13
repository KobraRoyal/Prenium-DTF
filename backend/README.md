# Backend Django

Le backend contient l'application Django principale du projet, exécutée dans le service Docker `web`.

## Organisation

- `apps/` : domaines métier
- `config/` : settings Django et configuration projet
- `requirements/` : dépendances `prod` et `dev`
- `templates/` : templates Django et fragments HTMX
- `static_src/` : sources CSS / JS

## Apps métier

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

## Settings

Répertoires principaux :

- `config/settings/base.py`
- `config/settings/dev.py`
- `config/settings/prod.py`
- `config/settings/test.py`

## Commandes utiles sous Docker

Raccourcis depuis la racine du dépôt :

```bash
make check
make migrations-plan
make test
make test-ui
make test-orders
make lint
make format
make audit
make shell
```

Check Django :

```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```

Migrations :

```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py showmigrations'
docker compose exec web sh -lc 'cd /app/backend && python manage.py makemigrations --check --dry-run'
docker compose exec web sh -lc 'cd /app/backend && python manage.py migrate'
```

Shell Django :

```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py shell'
```

Tests ciblés :

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/orders tests/uploads'
```

Qualité :

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend tests'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend tests'
```

## Notes

- le runtime local passe par Docker Compose, pas par un lancement Python direct ;
- le service `worker` exécute Celery ;
- le reverse proxy HTTP passe par `nginx` sur `localhost:8080`.
