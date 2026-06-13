# Sprint 3 — Performance et robustesse métier

## Ticket SPRINT-3.1 — Paginer les listes commandes API et portail

## Objectif

Bor­ner les listes commandes côté API et portail pour éviter une croissance non maîtrisée du temps de rendu et du volume en mémoire.

## Fichiers modifiés

- `backend/apps/orders/services/orders.py`
- `backend/apps/orders/views.py`
- `backend/apps/portal/views.py`
- `backend/config/settings/base.py`
- `.env.example`
- `backend/templates/portal/client/orders_list.html`
- `backend/templates/portal/staff/orders_list.html`
- `tests/orders/test_order_api.py`
- `tests/ui/test_portal_ui.py`
- `docs/sprints/sprint-3-performance-robustesse-metier.md`

## Résumé technique

Les vues de liste client et staff utilisent désormais une pagination bornée :

- API : réponse paginée avec bloc `pagination`
- Portail : navigation `Précédente` / `Suivante` et indication de page

Le service commandes sépare aussi les querysets de liste et de détail :

- listes : préchargent uniquement les lignes de commande
- détails : conservent le préchargement des uploads et inspections

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/orders/test_order_api.py tests/ui/test_portal_ui.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/orders backend/apps/portal tests/orders/test_order_api.py tests/ui/test_portal_ui.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/orders backend/apps/portal tests/orders/test_order_api.py tests/ui/test_portal_ui.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Les listes commandes API et portail ne renvoient qu’une page bornée.
- Les métadonnées de pagination sont disponibles côté API.
- Le détail de commande garde son comportement existant.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/orders/test_order_api.py tests/ui/test_portal_ui.py'` : OK, 20 tests passants.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/orders backend/apps/portal tests/orders/test_order_api.py tests/ui/test_portal_ui.py'` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/orders backend/apps/portal tests/orders/test_order_api.py tests/ui/test_portal_ui.py'` : OK.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `curl --fail http://localhost:8080/healthz/` : OK.

## Risques restants

- La réponse API liste inclut encore les items de commande ; une version allégée dédiée pourrait être envisagée plus tard si le volume grossit encore.
- Les paramètres de taille de page devront être ajustés en production selon l’usage réel.

## Éléments reportés

- Verrouillage concurrent des transitions production.
- Tests de nombre de requêtes SQL.

## Message de commit recommandé

```text
perf: paginate order lists in api and portal
```

## Ticket SPRINT-3.2 — Verrouiller les transitions production

## Objectif

Empêcher qu’une transition atelier soit validée à partir d’un état devenu obsolète entre la lecture et l’écriture.

## Fichiers modifiés

- `backend/apps/production/services/workflow.py`
- `tests/production/test_workflow_service.py`
- `docs/sprints/sprint-3-performance-robustesse-metier.md`

## Résumé technique

Le service de workflow recharge désormais `ProductionJob` sous `select_for_update()` dans la transaction avant de valider `from_status`.

La validation de transition ne se base plus sur l’objet potentiellement stale reçu par le service, mais sur l’état effectivement verrouillé en base.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/production/test_workflow_service.py tests/production/test_workflow_api.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/production tests/production'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/production tests/production'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Une transition concurrente déjà appliquée ne peut pas être rejouée à partir d’un objet stale.
- L’historique des transitions reste cohérent.
- Le workflow nominal API et scan reste inchangé.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/production/test_workflow_service.py tests/production/test_workflow_api.py'` : OK, 23 tests passants.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/production tests/production'` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/production tests/production'` : OK.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `curl --fail http://localhost:8080/healthz/` : OK.

## Risques restants

- Ce lot verrouille correctement le job atelier, mais ne couvre pas encore des scénarios de contention plus larges entre domaines applicatifs.
- Les tests actuels restent mono-processus ; un test multi-thread/process pourrait compléter plus tard la couverture.

## Éléments reportés

- Tests de charge / contention plus poussés.
- Mesure explicite du nombre de requêtes sur les écrans atelier.

## Message de commit recommandé

```text
robustness: lock production workflow transitions
```
