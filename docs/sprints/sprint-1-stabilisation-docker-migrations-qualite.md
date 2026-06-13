# Sprint 1 — Stabilisation Docker, migrations et qualité

## Ticket SPRINT-1.1 — Sécuriser le contexte Docker

## Objectif

Empêcher les fichiers d’environnement réels (`.env`, `.env.*`) d’entrer dans le contexte de build Docker, tout en conservant le fichier d’exemple `.env.example`.

## Fichiers modifiés

- `.dockerignore`
- `docs/sprints/sprint-1-stabilisation-docker-migrations-qualite.md`

## Résumé technique

Le build Docker du backend copie le contexte complet avec `COPY . /app`. Sans exclusion explicite, un fichier `.env` local peut être envoyé au daemon Docker et potentiellement être embarqué dans une image.

Correction appliquée :

```dockerignore
.env
.env.*
!.env.example
```

Le fichier `.env.example` reste disponible comme modèle de configuration, mais les fichiers contenant des secrets réels sont exclus du contexte de build.

## Commandes Docker de validation

```bash
docker compose build --no-cache web worker
docker compose up -d db redis web worker nginx
docker compose ps
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Les images `web` et `worker` se reconstruisent correctement.
- Les services `db`, `redis`, `web`, `worker` et `nginx` sont démarrés.
- `docker compose ps` indique des services actifs et sains.
- `python manage.py check` ne signale aucun problème.
- `http://localhost:8080/healthz/` répond avec un statut applicatif OK.

## Risques restants

- Si une image Docker contenant déjà `.env` a été poussée, partagée ou sauvegardée, les secrets concernés doivent être considérés comme exposés.
- Cette correction empêche l’inclusion future dans le contexte de build, mais ne supprime pas les secrets de vieilles images, caches Docker, registres ou sauvegardes.

## Note opérationnelle

Après cette correction, reconstruire les images :

```bash
docker compose build --no-cache web worker
```

Tourner les secrets si une image contenant `.env` a déjà été poussée, partagée ou rendue accessible hors de la machine locale.

## Éléments reportés

- Génération des migrations manquantes.
- Correction Ruff et formatage.
- Ajout de `pip-audit`.
- Durcissement upload, PayPal et rate-limit.
- Séparation Docker dev/prod.

## Message de commit recommandé

```text
security: exclude env files from docker build context
```

## Ticket SPRINT-1.2 — Stabiliser les migrations Django

## Objectif

Aligner les modèles Django avec les migrations versionnées afin que `makemigrations --check --dry-run` ne détecte plus de dérive de schéma.

## Fichiers modifiés

- `backend/apps/billing/migrations/0004_alter_invoice_options_and_more.py`
- `backend/apps/customers/migrations/0006_alter_customerbillingprofile_price_per_sqm_eur.py`
- `docs/sprints/sprint-1-stabilisation-docker-migrations-qualite.md`

## Résumé technique

Deux migrations ont été générées via Docker :

- `billing` : mise à jour des options du modèle `Invoice` et renommage de l’index `paid_at`.
- `customers` : alignement du champ `CustomerBillingProfile.price_per_sqm_eur`.

## Commandes Docker de validation

```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py makemigrations --check --dry-run'
docker compose exec web sh -lc 'cd /app/backend && python manage.py migrate --plan'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```

## Résultat attendu

- `makemigrations --check --dry-run` ne détecte plus de migration manquante.
- `migrate --plan` liste les migrations à appliquer si la base ne les a pas encore reçues.
- `python manage.py check` ne signale aucun problème.

## Risques restants

- Les migrations sont générées mais ne sont pas appliquées par ce ticket.
- Le renommage d’index doit être validé sur PostgreSQL lors de l’application effective des migrations.

## Éléments reportés

- Exécution réelle de `python manage.py migrate` en production.
- Checks qualité Docker.
- Ruff et formatage.
- Ajout de `pip-audit`.

## Message de commit recommandé

```text
db: add missing billing and customer migrations
```

## Ticket SPRINT-1.3 — Rendre les checks qualité exécutables sous Docker

## Objectif

Permettre l’exécution des contrôles qualité depuis Docker Compose, sans dépendre des outils installés sur la machine hôte.

## Fichiers modifiés

- `infra/docker/backend/Dockerfile`
- `docker-compose.yml`
- `infra/README.md`
- `docs/sprints/sprint-1-stabilisation-docker-migrations-qualite.md`

## Résumé technique

Le Dockerfile backend expose maintenant une cible `dev` qui hérite du runtime applicatif et installe les dépendances de développement depuis `backend/requirements/dev.txt`.

Les services Compose `web` et `worker` construisent cette cible `dev`, ce qui rend disponibles les outils nécessaires aux contrôles de développement :

- `pytest`
- `ruff`
- `pre-commit`

Le Dockerfile conserve aussi une cible `prod` basée sur le runtime sans dépendances de développement. Les builds de production doivent utiliser cette cible dédiée.

## Commandes Docker de validation

```bash
docker compose build web worker
docker compose run --rm --entrypoint sh web -lc 'ruff --version && pytest --version'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Les images `web` et `worker` se construisent avec la cible `dev`.
- `ruff` et `pytest` sont disponibles dans le conteneur.
- `pytest` peut être lancé depuis Docker Compose.
- `ruff check .` et `ruff format --check .` sont exécutables sous Docker.

Les échecs Ruff préexistants restent attendus tant que SPRINT-1.4 n’est pas traité.

## Résultats de validation observés

- `docker compose build web worker` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'ruff --version && pytest --version'` : OK, `ruff 0.11.13` et `pytest 8.4.2`.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'` : OK, 189 tests passants.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `curl --fail http://localhost:8080/healthz/` : OK.
- `ruff check .` : exécutable, échoue sur l’erreur préexistante `E501` dans `backend/apps/prospects/stepper.py`.
- `ruff format --check .` : exécutable, échoue sur 36 fichiers à reformater.

## Risques restants

- Le Compose local utilise une image `dev` plus lourde que l’image runtime.
- Les builds de production doivent explicitement utiliser la cible `prod` ou une configuration Compose production séparée.
- Les erreurs Ruff et le formatage non conforme ne sont pas corrigés par ce ticket.

## Éléments reportés

- Correction Ruff et formatage : SPRINT-1.4.
- Ajout de `pip-audit` : SPRINT-1.5.
- Séparation formelle Compose dev/prod : sprint de durcissement Docker production.

## Message de commit recommandé

```text
devops: add docker dev target for quality checks
```

## Ticket SPRINT-1.4 — Corriger Ruff et formatage

## Objectif

Remettre les contrôles Ruff au vert sans changement fonctionnel : correction de l’erreur `E501` et application du formatage standard du projet.

## Fichiers modifiés

- `backend/apps/accounts/permissions.py`
- `backend/apps/billing/admin.py`
- `backend/apps/billing/apps.py`
- `backend/apps/billing/services/invoices.py`
- `backend/apps/billing/services/payments.py`
- `backend/apps/billing/services/paypal.py`
- `backend/apps/billing/urls.py`
- `backend/apps/billing/views.py`
- `backend/apps/catalog/admin.py`
- `backend/apps/catalog/apps.py`
- `backend/apps/catalog/models.py`
- `backend/apps/catalog/services/catalog.py`
- `backend/apps/catalog/urls.py`
- `backend/apps/core/management/commands/seed_sprint09_recipe.py`
- `backend/apps/customers/models.py`
- `backend/apps/orders/admin.py`
- `backend/apps/orders/apps.py`
- `backend/apps/orders/models.py`
- `backend/apps/orders/services/orders.py`
- `backend/apps/orders/urls.py`
- `backend/apps/portal/views.py`
- `backend/apps/production/apps.py`
- `backend/apps/production/services/scans.py`
- `backend/apps/prospects/stepper.py`
- `backend/apps/prospects/views.py`
- `backend/apps/shipping/apps.py`
- `backend/apps/shipping/services/__init__.py`
- `backend/apps/shipping/services/sendcloud.py`
- `backend/apps/uploads/apps.py`
- `backend/apps/uploads/services/drive.py`
- `backend/apps/uploads/services/uploads.py`
- `tests/billing/test_billing_api.py`
- `tests/prospects/test_prospect_tunnel.py`
- `tests/shipping/test_sendcloud_service.py`
- `tests/ui/test_shop_checkout_ui.py`
- `tests/uploads/test_drive_sync.py`
- `docs/sprints/sprint-1-stabilisation-docker-migrations-qualite.md`

## Résumé technique

Le formatage Ruff a été appliqué via Docker Compose sur les 36 fichiers signalés. La ligne trop longue dans `backend/apps/prospects/stepper.py` a été corrigée par le formatage automatique.

Aucun refactoring ni changement métier n’a été introduit dans ce ticket.

## Commandes Docker de validation

```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- `ruff check .` passe sans erreur.
- `ruff format --check .` confirme que tous les fichiers sont formatés.
- `python manage.py check` ne signale aucun problème.
- La suite de tests reste passante.
- Le healthcheck HTTP reste OK.

## Résultats de validation observés

- `ruff format .` : OK, 36 fichiers reformattés.
- `ruff check .` : OK, `All checks passed!`.
- `ruff format --check .` : OK, 175 fichiers déjà formatés.
- `python manage.py check` : OK.
- `PYTHONPATH=/app/backend pytest` : OK, 189 tests passants.

## Risques restants

- Cette PR touche beaucoup de fichiers, même si les changements sont mécaniques.
- La revue doit vérifier qu’aucun changement métier n’a été mélangé au formatage.
- Les migrations de SPRINT-1.2 restent générées mais non appliquées par ce ticket.

## Éléments reportés

- Ajout de `pip-audit` : SPRINT-1.5.
- Validation upload par signature réelle.
- Durcissement endpoint PayPal.
- Pagination et robustesse concurrente.

## Message de commit recommandé

```text
style: apply ruff formatting
```

## Ticket SPRINT-1.5 — Ajouter SCA Python

## Objectif

Rendre l’audit de dépendances Python exécutable sous Docker Compose et visible dans la CI.

## Fichiers modifiés

- `backend/requirements/dev.txt`
- `.github/workflows/ci.yml`
- `docs/sprints/sprint-1-stabilisation-docker-migrations-qualite.md`

## Résumé technique

`pip-audit` est ajouté aux dépendances de développement afin qu’il soit disponible dans la cible Docker `dev`.

La CI backend exécute maintenant un contrôle SCA Python sur `backend/requirements/prod.txt` après les checks Ruff. Le périmètre reste centré sur les dépendances de production pour éviter de bloquer le pipeline sur des outils de développement non embarqués en runtime.

## Commandes Docker de validation

```bash
docker compose build web worker
docker compose run --rm --entrypoint sh web -lc 'pip-audit --version'
docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- `pip-audit` est disponible dans le conteneur `web`.
- L’audit SCA Python s’exécute sous Docker Compose.
- La CI backend exécute automatiquement `pip-audit`.
- Aucun changement applicatif n’est introduit par ce ticket.

## Résultats de validation observés

- `docker compose build web worker` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'pip-audit --version'` : OK, `pip-audit 2.10.0`.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'` : OK, aucune vulnérabilité connue détectée.
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK.
- `docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'` : OK, 189 tests passants.
- `curl --fail http://localhost:8080/healthz/` : OK.

## Risques restants

- `pip-audit` peut faire échouer la CI si une vulnérabilité est détectée dans les dépendances de production.
- Le rapport dépend de l’état courant des bases de vulnérabilités au moment de l’exécution.
- Les dépendances restent gérées par plages de versions, donc la reproductibilité stricte n’est pas encore traitée.

## Éléments reportés

- Verrouillage des dépendances de production.
- Gestion des éventuels faux positifs ou exemptions `pip-audit`.
- Durcissement uploads, PayPal, pagination et robustesse concurrente.

## Message de commit recommandé

```text
ci: add python dependency audit
```
