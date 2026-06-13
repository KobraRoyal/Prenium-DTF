# Sprint 6 — Garde-fous architecture portail

## Ticket SPRINT-6.1 — Verrouiller la structure modulaire du portail

## Objectif

Ajouter un garde-fou de test pour éviter la réintroduction d'une façade `apps.portal.views` ou un retour de routes portail vers un module monolithique.

## Fichiers modifiés

- `tests/ui/test_portal_architecture.py`
- `docs/sprints/sprint-6-garde-fous-architecture-portail.md`
- `docs/sprints/SPRINTS_INDEX.md`

## Résumé technique

Le lot ajoute un test d'architecture léger qui vérifie deux choses :

- le fichier historique `backend/apps/portal/views.py` n'existe plus ;
- les routes portail critiques résolvent bien vers les modules spécialisés :
  - `views_auth.py`
  - `views_client.py`
  - `views_checkout.py`
  - `views_staff.py`
  - `views_staff_uploads.py`
  - `views_staff_production.py`
  - `views_staff_shipping.py`
  - `views_staff_billing.py`

Le but est de protéger la structure obtenue aux sprints 5.1 à 5.5 sans toucher au comportement applicatif.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui/test_portal_architecture.py tests/ui/test_portal_ui.py tests/ui/test_shop_checkout_ui.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui/test_portal_architecture.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui/test_portal_architecture.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- la structure modulaire du portail reste figée par test ;
- une réintroduction d'un module façade ou un mauvais branchement d'URL casse le test ;
- aucun comportement métier n'est modifié.

## Risques restants

- ce garde-fou couvre la structure des routes, pas l'intégralité des dépendances internes ;
- si de nouvelles routes staff/client apparaissent plus tard, le test devra être complété.

## Éléments reportés

- éventuel test d'architecture plus large sur les imports interdits entre modules portail ;
- éventuelle séparation future de `views_common.py` si sa taille recommence à croître.

## Résultats de validation observés

- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK
- les commandes Docker de validation listées ci-dessus ont été lancées dans cette session, mais le client Docker est resté bloqué sans retour exploitable ;
- le lot reste donc à confirmer par relance locale de `pytest`, `ruff` et `manage.py check` sous Docker.

## Message de commit recommandé

```text
test: add portal architecture guardrails
```

## Ticket SPRINT-6.2 — Verrouiller les frontières d'import du portail

## Objectif

Empêcher le retour d'un couplage implicite entre les modules portail après le découpage de Sprint 5.

## Fichiers modifiés

- `tests/ui/test_portal_architecture.py`
- `docs/sprints/sprint-6-garde-fous-architecture-portail.md`

## Résumé technique

Le lot complète le test d'architecture portail avec une analyse AST des imports Python.

Le test vérifie que :

- aucun module portail ne réimporte `apps.portal.views` ;
- chaque module garde uniquement les dépendances internes attendues ;
- les panneaux staff restent branchés sur `views_common.py`, `views_staff.py` et `htmx.py`, sans dépendances croisées inutiles.

Ce lot ne modifie pas le runtime applicatif.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui/test_portal_architecture.py tests/ui/test_portal_ui.py tests/ui/test_shop_checkout_ui.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check tests/ui/test_portal_architecture.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check tests/ui/test_portal_architecture.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- la structure d'import du portail devient explicitement testée ;
- une nouvelle dépendance transversale non prévue casse le test ;
- la modularisation du portail reste stable dans le temps.

## Risques restants

- le test contrôle les imports déclarés, pas les couplages dynamiques éventuels ;
- si un nouveau module portail apparaît, il faudra l'ajouter à la matrice d'import autorisée.

## Éléments reportés

- éventuelle règle d'architecture plus globale sur la taille maximale des modules portail ;
- éventuel garde-fou similaire pour d'autres apps monolithiques si le besoin apparaît.

## Résultats de validation observés

- À compléter après validation Docker.

## Message de commit recommandé

```text
test: enforce portal import boundaries
```

## Ticket SPRINT-6.3 — Verrouiller la taille des modules portail

## Objectif

Empêcher qu'un futur lot reconstitue progressivement un module portail trop volumineux.

## Fichiers modifiés

- `tests/ui/test_portal_architecture.py`
- `docs/sprints/sprint-6-garde-fous-architecture-portail.md`

## Résumé technique

Le lot ajoute une matrice simple de tailles maximales par module portail.

Le test couvre les modules spécialisés et `views_common.py`. L'objectif n'est pas de figer chaque ligne, mais de détecter une dérive nette de structure :

- `views_auth.py`
- `views_staff_uploads.py`
- `views_staff.py`
- `views_staff_billing.py`
- `views_staff_production.py`
- `views_staff_shipping.py`
- `views_common.py`
- `views_checkout.py`
- `views_client.py`

Les seuils sont définis légèrement au-dessus de l'état actuel pour autoriser les petites évolutions sans réintroduire un monolithe.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui/test_portal_architecture.py tests/ui/test_portal_ui.py tests/ui/test_shop_checkout_ui.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check tests/ui/test_portal_architecture.py'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check tests/ui/test_portal_architecture.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- une croissance anormale d'un module portail casse le test ;
- la structure modulaire reste visible et contrainte ;
- aucun comportement applicatif n'est modifié.

## Risques restants

- un seuil de taille reste un indicateur simple, pas un jugement de conception complet ;
- si un module doit grossir légitimement, il faudra ajuster explicitement le seuil dans le test.

## Éléments reportés

- éventuelle règle complémentaire sur le nombre de classes par module ;
- éventuel garde-fou similaire pour d'autres apps du monolithe si la même dérive apparaît.

## Résultats de validation observés

- À compléter après validation Docker.

## Message de commit recommandé

```text
test: add portal module size guardrails
```
