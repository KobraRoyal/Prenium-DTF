# Tests

Les tests sont organisés principalement par domaine métier, avec un sous-ensemble UI dédié.

## Arborescence actuelle

- `tests/accounts/`
- `tests/billing/`
- `tests/b2b_order_projects/`
- `tests/catalog/`
- `tests/core/`
- `tests/customers/`
- `tests/notifications/`
- `tests/orders/`
- `tests/production/`
- `tests/prospects/`
- `tests/shipping/`
- `tests/ui/`
- `tests/uploads/`
- `tests/conftest.py`

## Types de tests présents

- tests de services métier
- tests d'API Django / DRF
- tests UI Django / templates / HTMX
- tests de permissions et d'isolation
- tests de sécurité ciblés

## Lancer les tests sous Docker

Suite complète :

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'
```

Suites ciblées :

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/b2b_order_projects'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/production tests/shipping'
make test-ui
make test-orders
```

## Garde-fous qualité

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check tests'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check tests'
```

## Notes

- les tests utilisent `config.settings.test` via `pyproject.toml` ;
- `tests/ui/test_portal_architecture.py` contient des garde-fous structurels sur le découpage du portail ;
- les commandes doivent être jouées sous Docker pour rester alignées avec l'environnement projet.
