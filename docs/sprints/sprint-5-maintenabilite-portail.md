# Sprint 5 — Maintenabilité portail

## Ticket SPRINT-5.1 — Préparer la structure modulaire des vues portail

## Objectif

Réduire la taille et le couplage de `backend/apps/portal/views.py` sans changer le comportement des routes existantes.

## Fichiers modifiés

- `backend/apps/portal/views.py`
- `backend/apps/portal/views_common.py`
- `backend/apps/portal/views_auth.py`
- `backend/apps/portal/urls.py`
- `tests/ui/test_shop_checkout_ui.py`
- `docs/sprints/sprint-5-maintenabilite-portail.md`

## Résumé technique

Le lot extrait les éléments transverses et stables du portail :

- `PortalLoginView` et `PortalLogoutView` dans `views_auth.py` ;
- les services partagés, mixins d’accès et helpers de présentation dans `views_common.py`.

Les vues client, checkout et staff restent dans `views.py` pour éviter un refactoring large dès ce premier lot. Les routes et noms de vues restent inchangés.

Le test UI d’upload checkout utilise désormais un en-tête PNG valide, cohérent avec le durcissement de validation déjà en place sur les uploads.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- Les routes portail continuent de résoudre les mêmes vues.
- Les tests UI portail restent passants.
- Le découpage de base pour les prochains lots est en place.

## Risques restants

- Les vues client, checkout et staff sont encore concentrées dans `views.py`.
- Une extraction plus large pourra exposer des imports circulaires si elle mélange helpers et vues métier dans le même lot.

## Éléments reportés

- Extraction des vues client et checkout.
- Extraction des vues staff et panneaux HTMX.
- Mutualisation plus poussée des contextes récurrents.

## Résultats de validation observés

- `docker compose build web worker` : OK
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui'` : OK, 19 tests passants
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'` : OK
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui'` : OK
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK

## Message de commit recommandé

```text
refactor: prepare portal views module structure
```

## Ticket SPRINT-5.2 — Extraire les vues client et checkout

## Objectif

Sortir les vues client et checkout du fichier central `backend/apps/portal/views.py` sans modifier les routes ni les templates.

## Fichiers modifiés

- `backend/apps/portal/views.py`
- `backend/apps/portal/views_client.py`
- `backend/apps/portal/views_checkout.py`
- `backend/apps/portal/urls.py`
- `docs/sprints/sprint-5-maintenabilite-portail.md`

## Résumé technique

Les vues client sont déplacées dans `views_client.py` et les vues checkout dans `views_checkout.py`.

`urls.py` importe désormais explicitement ces vues depuis leurs modules dédiés. `views.py` conserve la surface staff et les panneaux HTMX staff.

Les URLs et noms de routes restent inchangés.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- Les parcours client portail continuent de fonctionner.
- Le checkout client reste inchangé côté utilisateur.
- `views.py` est significativement allégé.

## Risques restants

- La partie staff et ses panneaux restent encore concentrés dans `views.py`.
- Une extraction ultérieure des panneaux staff devra surveiller de près les dépendances HTMX et permissions fines.

## Éléments reportés

- Extraction des vues staff.
- Extraction des panneaux HTMX staff par domaine.
- Mutualisation plus poussée des contextes client.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'` : OK, 102 tests passants
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'` : OK
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'` : OK
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK

## Message de commit recommandé

```text
refactor: extract client and checkout portal views
```

## Ticket SPRINT-5.3 — Extraire le noyau staff du portail

## Objectif

Sortir les vues staff principales de `backend/apps/portal/views.py` en gardant les panneaux HTMX staff dans le fichier central pour un lot séparé.

## Fichiers modifiés

- `backend/apps/portal/views.py`
- `backend/apps/portal/views_staff.py`
- `backend/apps/portal/urls.py`
- `docs/sprints/sprint-5-maintenabilite-portail.md`

## Résumé technique

Les vues suivantes sont déplacées dans `views_staff.py` :

- `StaffDashboardView`
- `StaffOrderListView`
- `StaffOrderContextMixin`
- `StaffOrderDetailView`
- `StaffOrderPriceView`

`views.py` conserve les panneaux HTMX staff et les mutations associées. Les URLs et noms de routes restent inchangés.

Après extraction, `backend/apps/portal/views.py` descend à 493 lignes et se concentre sur les panneaux HTMX staff.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- Le parcours staff principal reste inchangé.
- `views.py` se concentre davantage sur les panneaux HTMX staff.
- La prochaine extraction pourra cibler les panneaux par domaine métier.

## Risques restants

- Les panneaux staff restent nombreux dans `views.py`.
- Les futurs lots devront gérer finement les dépendances entre `StaffOrderContextMixin` et les panneaux HTMX.

## Éléments reportés

- Extraction des panneaux production/shipping/billing.
- Découpage final de `views.py` en modules métier staff.
- Mutualisation plus poussée des toasts et contextes staff.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'` : OK, 102 tests passants
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'` : OK
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'` : OK
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK

## Message de commit recommandé

```text
refactor: extract staff portal core views
```

## Ticket SPRINT-5.4 — Extraire les panneaux HTMX staff par domaine

## Objectif

Sortir les panneaux staff HTMX du fichier central `backend/apps/portal/views.py` vers des modules métier dédiés, sans modifier les URLs ni les templates.

## Fichiers modifiés

- `backend/apps/portal/views.py`
- `backend/apps/portal/views_staff_uploads.py`
- `backend/apps/portal/views_staff_production.py`
- `backend/apps/portal/views_staff_shipping.py`
- `backend/apps/portal/views_staff_billing.py`
- `backend/apps/portal/urls.py`
- `docs/sprints/sprint-5-maintenabilite-portail.md`

## Résumé technique

Les panneaux staff sont désormais séparés par domaine :

- `views_staff_uploads.py` pour uploads, inspection et Drive Sync ;
- `views_staff_production.py` pour production et scan ;
- `views_staff_shipping.py` pour expédition et synchronisation de suivi ;
- `views_staff_billing.py` pour facturation et marquage manuel de facture payée.

`views.py` devient un point d’entrée léger qui ré-exporte ces vues pour compatibilité interne éventuelle. Les routes continuent d’utiliser les mêmes noms.

Après extraction, `backend/apps/portal/views.py` descend à 20 lignes et sert uniquement de façade de compatibilité.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- Les panneaux staff continuent de répondre aux mêmes URLs HTMX.
- `views.py` ne porte plus la logique métier des panneaux.
- Le prochain lot peut viser un éventuel affinage des helpers restants sans toucher aux routes.

## Risques restants

- La logique partagée de contexte staff repose encore sur `StaffOrderContextMixin`.
- `views.py` reste présent comme façade de compatibilité ; il faudra décider plus tard s’il doit rester ou disparaître.

## Éléments reportés

- Éventuelle fusion ou rationalisation de certains helpers de contexte staff.
- Vérification d’éventuels imports externes encore dépendants de `apps.portal.views`.
- Nettoyage final de la façade `views.py` si elle devient inutile.

## Résultats de validation observés

- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'` : OK, 102 tests passants
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'` : OK
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'` : OK
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK

## Message de commit recommandé

```text
refactor: split staff portal panels by domain
```

## Ticket SPRINT-5.5 — Supprimer la façade portail devenue inutile

## Objectif

Retirer `backend/apps/portal/views.py` maintenant que les routes et imports internes pointent directement vers les modules spécialisés.

## Fichiers modifiés

- `backend/apps/portal/views.py`
- `docs/sprints/sprint-5-maintenabilite-portail.md`

## Résumé technique

Une vérification des imports Python du projet ne montre plus de dépendance interne vers `apps.portal.views`.

Le module façade `views.py`, réduit à un simple ré-export au sprint précédent, est donc supprimé. La structure du portail repose désormais uniquement sur :

- `views_auth.py`
- `views_client.py`
- `views_checkout.py`
- `views_staff.py`
- `views_staff_uploads.py`
- `views_staff_production.py`
- `views_staff_shipping.py`
- `views_staff_billing.py`
- `views_common.py`

Ce lot ne change aucune URL ni aucun comportement applicatif.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check backend/apps/portal tests/ui tests/orders tests/uploads'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- Le portail continue de fonctionner sans module façade.
- Les imports du projet restent explicites et par domaine.
- La structure finale du portail est stabilisée.

## Risques restants

- Un code externe au dépôt pourrait encore importer `apps.portal.views`.
- `views_common.py` reste le point principal de mutualisation ; il faudra éviter d’y re-concentrer trop de logique.

## Éléments reportés

- Ajouter, si nécessaire plus tard, un test ciblé d’architecture pour interdire la réintroduction d’un module façade.
- Revoir à terme si certains helpers de `views_common.py` doivent être déplacés vers des services ou presenters plus spécialisés.

## Résultats de validation observés

- Vérification structurelle des imports projet : aucune dépendance interne restante vers `apps.portal.views`.
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK
- Les commandes Docker de validation listées ci-dessus ont été relancées mais le client Docker est resté bloqué dans cette session ; elles sont à rejouer localement pour confirmer le lot de suppression de façade.

## Message de commit recommandé

```text
refactor: remove obsolete portal views facade
```
