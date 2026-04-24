# Roadmap de sprints post-audit Docker

## Vue d’ensemble

| Sprint | Objectif principal | PR incluses | Priorité | Durée estimée | Risque |
|---|---|---|---|---|---|
| Sprint 1 | Stabiliser le socle Docker, migrations et qualité | PR 1, PR 2, PR 3, PR 4, PR 5 | Critique | 3 à 5 jours | Moyen |
| Sprint 2 | Fermer les risques sécurité applicative ciblés | PR 6, PR 7, IP proxy/rate-limit | Élevée | 1 à 2 semaines | Moyen |
| Sprint 3 | Améliorer performance et robustesse métier | PR 8, PR 9 | Élevée | 1 à 2 semaines | Moyen |
| Sprint 4 | Durcir l’exécution Docker production | PR 10 | Moyenne/Élevée | 1 semaine | Moyen à élevé |
| Sprint 5 | Réduire la dette de maintenabilité portail | PR 11 | Moyenne | 1 à 2 semaines | Moyen |

## Sprint 1 — Stabilisation critique Docker, migrations et qualité

Objectif du sprint : fermer les risques immédiats qui peuvent casser un déploiement ou exposer des secrets, puis rendre les validations qualité reproductibles sous Docker.

Périmètre inclus :
- Sécurisation du contexte Docker.
- Migrations manquantes.
- Outillage qualité Docker.
- Ruff/formatage.
- Audit dépendances Python.

Hors périmètre :
- Refactoring `portal/views.py`.
- Changements métier.
- Pagination.
- Durcissement upload/PayPal.

### Ticket SPRINT-1.1 — Sécuriser le contexte Docker
- Type : Sécurité / DevOps
- Priorité : Critique
- Objectif : empêcher `.env` et `.env.*` d’être copiés dans l’image Docker.
- Fichiers probables : `.dockerignore`, `docs/security/SECURITY_BASELINE.md` ou `infra/README.md`
- Étapes techniques :
  - Ajouter `.env` et `.env.*` dans `.dockerignore`.
  - Conserver `!.env.example`.
  - Documenter rebuild image et rotation secrets si image déjà poussée.
  - Vérifier que `docker-compose.yml` continue d’utiliser `.env` via `env_file`.
- Critères d’acceptation :
  - `.env` reste utilisable au runtime Compose.
  - `.env` n’entre plus dans le contexte build.
  - Documentation de remédiation présente.
- Commandes Docker de validation :
```bash
docker compose build --no-cache web worker
docker compose ps
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```
- Risques : oublier la rotation des secrets si une image exposée existe déjà.
- Dépendances : aucune.
- Message de commit recommandé : `security: exclude env files from docker build context`

### Ticket SPRINT-1.2 — Stabiliser les migrations Django
- Type : Migration
- Priorité : Élevée
- Objectif : aligner modèles Django et migrations.
- Fichiers probables : `backend/apps/billing/migrations/*`, `backend/apps/customers/migrations/*`
- Étapes techniques :
  - Générer les migrations détectées.
  - Relire les opérations générées.
  - Vérifier compatibilité PostgreSQL.
- Critères d’acceptation :
  - `makemigrations --check --dry-run` ne propose plus de migration.
  - `migrate --plan` est lisible et cohérent.
- Commandes Docker de validation :
```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py makemigrations --check --dry-run'
docker compose exec web sh -lc 'cd /app/backend && python manage.py migrate --plan'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```
- Risques : renommage d’index ou altération inattendue de champ.
- Dépendances : SPRINT-1.1 recommandé avant rebuild, mais non bloquant.
- Message de commit recommandé : `db: add missing billing and customer migrations`

### Ticket SPRINT-1.3 — Rendre les checks qualité exécutables sous Docker
- Type : DevOps / Qualité
- Priorité : Élevée
- Objectif : permettre `pytest`, `ruff`, `pip-audit` depuis Docker Compose.
- Fichiers probables : `docker-compose.yml`, `infra/docker/backend/Dockerfile`, `backend/requirements/dev.txt`, `infra/README.md`
- Étapes techniques :
  - Choisir une approche dev sans alourdir prod : service/target dev ou commande dédiée.
  - Installer les dépendances dev uniquement pour les validations.
  - Documenter les commandes Docker.
- Critères d’acceptation :
  - Les checks qualité s’exécutent sans dépendre de l’hôte.
  - L’image prod reste maîtrisée.
- Commandes Docker de validation :
```bash
docker compose build web
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest'
```
- Risques : mélanger dev/prod dans la même image.
- Dépendances : SPRINT-1.1.
- Message de commit recommandé : `devops: make quality checks runnable with docker compose`

### Ticket SPRINT-1.4 — Corriger Ruff et formatage
- Type : Qualité
- Priorité : Élevée
- Objectif : remettre lint et format au vert sans changement fonctionnel.
- Fichiers probables : `backend/apps/prospects/stepper.py` + fichiers formatés par Ruff
- Étapes techniques :
  - Corriger la ligne trop longue.
  - Appliquer le formatage.
  - Ne faire aucun changement métier.
- Critères d’acceptation :
  - `ruff check .` OK.
  - `ruff format --check .` OK.
  - Tests inchangés fonctionnellement.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest'
```
- Risques : PR volumineuse en fichiers mais faible en logique.
- Dépendances : SPRINT-1.3.
- Message de commit recommandé : `style: apply ruff formatting`

### Ticket SPRINT-1.5 — Ajouter SCA Python
- Type : Sécurité / Qualité
- Priorité : Élevée
- Objectif : rendre visibles les vulnérabilités Python en CI et Docker.
- Fichiers probables : `backend/requirements/dev.txt`, `.github/workflows/ci.yml`, `infra/README.md`
- Étapes techniques :
  - Ajouter `pip-audit`.
  - Ajouter une étape CI.
  - Documenter la commande Docker.
- Critères d’acceptation :
  - Audit Python exécutable sous Docker.
  - CI échoue ou remonte explicitement les vulnérabilités selon politique définie.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'
```
- Risques : faux positifs ou dépendances transitoires à arbitrer.
- Dépendances : SPRINT-1.3.
- Message de commit recommandé : `security: add python dependency audit`

Backlog Sprint 1 :

| ID | Titre | Type | Priorité | Effort estimé | Dépendance | Statut |
|---|---|---|---|---|---|---|
| SPRINT-1.1 | Sécuriser le contexte Docker | Sécurité | Critique | 0.5 j | Aucune | À faire |
| SPRINT-1.2 | Stabiliser les migrations Django | Migration | Élevée | 0.5 j | Aucune | À faire |
| SPRINT-1.3 | Checks qualité sous Docker | DevOps | Élevée | 1 j | 1.1 | À faire |
| SPRINT-1.4 | Corriger Ruff/formatage | Qualité | Élevée | 0.5 j | 1.3 | À faire |
| SPRINT-1.5 | Ajouter SCA Python | Sécurité | Élevée | 0.5 j | 1.3 | À faire |

Livrables :
- `.dockerignore` sécurisé.
- Migrations alignées.
- Checks qualité Docker disponibles.
- Ruff/format au vert.
- Audit dépendances Python activé.

Définition de Done :
- Tous les tickets du sprint sont en PR atomiques.
- Toutes les commandes Docker du sprint passent.
- Documentation minimale mise à jour.
- Aucun changement métier mélangé au formatage.

## Sprint 2 — Sécurité applicative ciblée

Objectif du sprint : réduire les risques d’entrée malveillante et de contournement sur les flux sensibles upload, PayPal et login/proxy.

Périmètre inclus :
- Validation upload par contenu.
- Durcissement endpoint PayPal interne.
- Clarification IP proxy/rate-limit.

Hors périmètre :
- Pagination.
- Refactoring portail.
- Non-root Docker runtime.

### Ticket SPRINT-2.1 — Durcir validation des uploads
- Type : Sécurité
- Priorité : Élevée
- Objectif : ne plus faire confiance uniquement au MIME navigateur.
- Fichiers probables : `backend/apps/uploads/services/validation.py`, `tests/uploads/*`, éventuellement `backend/config/settings/base.py`
- Étapes techniques :
  - Ajouter détection signature PDF/PNG/JPEG/TIFF/PSD/AI.
  - Refuser incohérence extension/MIME/contenu.
  - Traiter SVG prudemment ou le sortir de l’allowlist si non indispensable.
  - Ajouter tests positifs/négatifs.
- Critères d’acceptation :
  - Fichier annoncé PDF mais contenu non PDF refusé.
  - Fichiers légitimes supportés acceptés.
  - Tests cross-upload existants passent.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/uploads tests/uploads'
```
- Risques : rejeter des fichiers clients réels, surtout AI/PSD si signature incomplète.
- Dépendances : Sprint 1 terminé.
- Message de commit recommandé : `security: validate uploaded files by content signature`

### Ticket SPRINT-2.2 — Durcir endpoint PayPal interne
- Type : Sécurité
- Priorité : Élevée
- Objectif : rendre le token interne plus sûr et tracer les refus.
- Fichiers probables : `backend/apps/billing/views.py`, `tests/billing/test_billing_api.py`, `backend/apps/auditlog/*`
- Étapes techniques :
  - Utiliser `secrets.compare_digest`.
  - Ajouter audit des refus token.
  - Garder le comportement nominal existant.
  - Ajouter tests refus token absent/invalide.
- Critères d’acceptation :
  - Callback valide fonctionne toujours.
  - Token invalide refusé.
  - Refus journalisé.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/billing tests/accounts/test_login_rate_limit.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```
- Risques : casser l’intégration interne PayPal si le header attendu change.
- Dépendances : Sprint 1 terminé.
- Message de commit recommandé : `security: harden internal paypal capture endpoint`

### Ticket SPRINT-2.3 — Clarifier IP proxy et rate-limit login
- Type : Sécurité / DevOps
- Priorité : Moyenne
- Objectif : éviter une confiance implicite dangereuse dans `X-Forwarded-For`.
- Fichiers probables : `backend/apps/accounts/middleware.py`, `infra/nginx/default.conf`, `docs/security/SECURITY_BASELINE.md`, tests accounts
- Étapes techniques :
  - Clarifier source IP attendue derrière Nginx.
  - Documenter le modèle de confiance proxy.
  - Ajuster si nécessaire pour privilégier `X-Real-IP` ou un header contrôlé.
  - Ajouter/adapter tests.
- Critères d’acceptation :
  - Le comportement rate-limit est documenté.
  - Les tests login rate-limit passent.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/accounts/test_login_rate_limit.py'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```
- Risques : bloquer trop agressivement des utilisateurs derrière proxy partagé.
- Dépendances : aucune, mais à faire après SPRINT-2.2.
- Message de commit recommandé : `security: document and harden login client ip handling`

Backlog Sprint 2 :

| ID | Titre | Type | Priorité | Effort estimé | Dépendance | Statut |
|---|---|---|---|---|---|---|
| SPRINT-2.1 | Durcir validation des uploads | Sécurité | Élevée | 3-5 j | Sprint 1 | À faire |
| SPRINT-2.2 | Durcir endpoint PayPal interne | Sécurité | Élevée | 1-2 j | Sprint 1 | À faire |
| SPRINT-2.3 | Clarifier IP proxy/rate-limit | Sécurité | Moyenne | 1 j | 2.2 | À faire |

Livrables :
- Validation upload renforcée.
- Endpoint PayPal interne durci.
- Modèle IP/rate-limit documenté et testé.

Définition de Done :
- Tests sécurité ciblés passants sous Docker.
- Aucun refactoring portail inclus.
- Documentation sécurité mise à jour.
- Comportement nominal préservé.

## Sprint 3 — Performance et robustesse métier

Objectif du sprint : stabiliser les volumes de données et éviter les incohérences concurrentes sur workflow production.

Périmètre inclus :
- Pagination commandes API/portail.
- Querysets liste/détail plus légers.
- Lock transactionnel sur transitions production.

Hors périmètre :
- Refactoring massif portail.
- Async Sendcloud complet.
- Durcissement Docker runtime.

### Ticket SPRINT-3.1 — Ajouter pagination commandes API
- Type : Performance
- Priorité : Élevée
- Objectif : borner les réponses API staff/client.
- Fichiers probables : `backend/apps/orders/views.py`, `backend/apps/orders/services/orders.py`, `tests/orders/*`
- Étapes techniques :
  - Ajouter pagination compatible.
  - Ne pas casser les champs existants.
  - Ajouter tests page par défaut et page suivante.
- Critères d’acceptation :
  - Liste API bornée.
  - Tests commandes passants.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/orders'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/orders tests/orders'
```
- Risques : changement de contrat API.
- Dépendances : Sprint 1.
- Message de commit recommandé : `perf: paginate order api lists`

### Ticket SPRINT-3.2 — Ajouter pagination portail commandes
- Type : Performance
- Priorité : Élevée
- Objectif : éviter rendu non borné dans les pages client/staff.
- Fichiers probables : `backend/apps/portal/views.py`, `backend/templates/portal/client/orders_list.html`, `backend/templates/portal/staff/orders_list.html`, `tests/ui/*`
- Étapes techniques :
  - Ajouter pagination Django.
  - Conserver UX existante.
  - Ajouter tests UI/template.
- Critères d’acceptation :
  - Pages listes bornées.
  - Navigation pagination visible.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/ui tests/orders'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
```
- Risques : régression UI HTMX ou templates.
- Dépendances : SPRINT-3.1 recommandé.
- Message de commit recommandé : `perf: paginate portal order lists`

### Ticket SPRINT-3.3 — Séparer querysets liste/détail
- Type : Performance
- Priorité : Moyenne
- Objectif : éviter les `prefetch_related` lourds sur les listes.
- Fichiers probables : `backend/apps/orders/services/orders.py`, tests orders/ui
- Étapes techniques :
  - Créer queryset léger pour listes.
  - Garder queryset complet pour détails.
  - Ajouter tests de non-régression.
- Critères d’acceptation :
  - Listes fonctionnelles.
  - Détails conservent uploads/items.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/orders tests/ui'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/orders backend/apps/portal'
```
- Risques : oubli de données attendues dans les templates.
- Dépendances : SPRINT-3.1, SPRINT-3.2.
- Message de commit recommandé : `perf: split order list and detail querysets`

### Ticket SPRINT-3.4 — Verrouiller transitions production
- Type : Robustesse
- Priorité : Moyenne
- Objectif : éviter incohérences lors de transitions concurrentes.
- Fichiers probables : `backend/apps/production/services/workflow.py`, `tests/production/*`
- Étapes techniques :
  - Recharger `ProductionJob` avec `select_for_update` dans la transaction.
  - Valider `from_status` après lock.
  - Ajouter test de comportement transactionnel si réaliste.
- Critères d’acceptation :
  - Transitions existantes passent.
  - Refus cohérent si statut changé entre-temps.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/production'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```
- Risques : deadlocks si ordre de lock mal maîtrisé.
- Dépendances : Sprint 1.
- Message de commit recommandé : `fix: lock production job during status transition`

Backlog Sprint 3 :

| ID | Titre | Type | Priorité | Effort estimé | Dépendance | Statut |
|---|---|---|---|---|---|---|
| SPRINT-3.1 | Pagination API commandes | Performance | Élevée | 2 j | Sprint 1 | À faire |
| SPRINT-3.2 | Pagination portail commandes | Performance | Élevée | 2 j | 3.1 | À faire |
| SPRINT-3.3 | Querysets liste/détail | Performance | Moyenne | 1-2 j | 3.1, 3.2 | À faire |
| SPRINT-3.4 | Lock transitions production | Robustesse | Moyenne | 1 j | Sprint 1 | À faire |

Livrables :
- Listes bornées.
- Querysets plus sobres.
- Workflow production plus robuste.

Définition de Done :
- Tests orders, UI et production passants.
- Pagination rétrocompatible autant que possible.
- Aucune refonte portail incluse.

## Sprint 4 — Durcissement Docker production

Objectif du sprint : préparer une exécution Docker plus sûre et plus claire pour la production.

Périmètre inclus :
- Runtime web non-root.
- Séparation dev/prod.
- Documentation Redis non persistant.
- Documentation migrations au démarrage.
- Clarification des volumes.

Hors périmètre :
- Refactoring applicatif.
- Pagination.
- Changements métier.

### Ticket SPRINT-4.1 — Préparer runtime web non-root
- Type : DevOps / Sécurité
- Priorité : Moyenne
- Objectif : éviter l’exécution web en root.
- Fichiers probables : `infra/docker/backend/Dockerfile`, `infra/scripts/web-entrypoint.sh`
- Étapes techniques :
  - Créer utilisateur applicatif.
  - Ajuster droits `/app`, statiques, médias.
  - Vérifier Gunicorn et collectstatic.
- Critères d’acceptation :
  - `id` dans `web` n’est pas root.
  - `check`, `migrate --plan`, healthcheck OK.
- Commandes Docker de validation :
```bash
docker compose build --no-cache web worker
docker compose up -d db redis web worker nginx
docker compose exec web sh -lc 'id && cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```
- Risques : permissions médias/statiques cassées.
- Dépendances : Sprint 1.
- Message de commit recommandé : `security: run django web container as non-root`

### Ticket SPRINT-4.2 — Clarifier séparation Docker dev/prod
- Type : DevOps / Documentation
- Priorité : Moyenne
- Objectif : éviter que le compose dev soit pris pour un compose prod.
- Fichiers probables : `docker-compose.yml`, éventuel `docker-compose.override.yml`, `infra/README.md`
- Étapes techniques :
  - Documenter volumes bind mount comme usage dev.
  - Proposer convention prod sans bind mount.
  - Ne pas casser l’environnement actuel.
- Critères d’acceptation :
  - Usage dev/prod clair.
  - Commandes de lancement documentées.
- Commandes Docker de validation :
```bash
docker compose config
docker compose ps
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```
- Risques : confusion si trop de fichiers Compose.
- Dépendances : SPRINT-4.1 recommandé.
- Message de commit recommandé : `docs: clarify docker dev and production usage`

### Ticket SPRINT-4.3 — Documenter Redis non persistant
- Type : Documentation / DevOps
- Priorité : Faible
- Objectif : expliciter que Redis sert cache/broker et n’est pas durable.
- Fichiers probables : `infra/README.md`, `docs/security/SECURITY_BASELINE.md`
- Étapes techniques :
  - Documenter `--save "" --appendonly no`.
  - Indiquer impact sur tâches/résultats Celery.
- Critères d’acceptation :
  - Risque opérationnel documenté.
- Commandes Docker de validation :
```bash
docker compose exec redis redis-cli ping
docker compose ps
```
- Risques : aucun code.
- Dépendances : aucune.
- Message de commit recommandé : `docs: document redis persistence tradeoff`

### Ticket SPRINT-4.4 — Documenter migrations au démarrage
- Type : Documentation / DevOps
- Priorité : Moyenne
- Objectif : clarifier le risque de `python manage.py migrate` dans `web-entrypoint`.
- Fichiers probables : `infra/scripts/web-entrypoint.sh`, `infra/README.md`
- Étapes techniques :
  - Documenter comportement actuel.
  - Ajouter recommandation release/rollback.
  - Ne pas changer encore le mode d’exécution sans décision ops.
- Critères d’acceptation :
  - Runbook de déploiement clair.
- Commandes Docker de validation :
```bash
docker compose exec web sh -lc 'cd /app/backend && python manage.py migrate --plan'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
```
- Risques : laisser un risque connu mais documenté.
- Dépendances : Sprint 1.
- Message de commit recommandé : `docs: document migration startup strategy`

Backlog Sprint 4 :

| ID | Titre | Type | Priorité | Effort estimé | Dépendance | Statut |
|---|---|---|---|---|---|---|
| SPRINT-4.1 | Runtime web non-root | DevOps | Moyenne | 2-3 j | Sprint 1 | À faire |
| SPRINT-4.2 | Séparation dev/prod | DevOps | Moyenne | 1 j | 4.1 | À faire |
| SPRINT-4.3 | Redis non persistant | Documentation | Faible | 0.5 j | Aucune | À faire |
| SPRINT-4.4 | Migrations au démarrage | Documentation | Moyenne | 0.5 j | Sprint 1 | À faire |

Livrables :
- Image runtime plus sûre.
- Runbook Docker plus clair.
- Risques Redis/migrations documentés.

Définition de Done :
- Build Docker complet OK.
- Services healthy.
- Healthcheck `localhost:8080` OK.
- Documentation infra mise à jour.

## Sprint 5 — Maintenabilité portail

Objectif du sprint : réduire la dette structurelle de `portal/views.py` sans changer le comportement utilisateur.

Périmètre inclus :
- Découpage progressif.
- Préservation des routes et noms de vues.
- Tests UI/portail.

Hors périmètre :
- Nouveaux écrans.
- Refonte UX.
- Changements sécurité ou performance non liés.

### Ticket SPRINT-5.1 — Préparer structure de modules portail
- Type : Refactoring
- Priorité : Moyenne
- Objectif : créer une structure cible sans déplacer toute la logique d’un coup.
- Fichiers probables : `backend/apps/portal/views.py`, nouveaux modules `backend/apps/portal/views_client.py`, `views_checkout.py`, `views_staff.py` ou package équivalent
- Étapes techniques :
  - Choisir structure simple.
  - Déplacer helpers communs si nécessaire.
  - Garder imports compatibles.
- Critères d’acceptation :
  - Routes inchangées.
  - Tests UI passent.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/ui'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
```
- Risques : imports circulaires.
- Dépendances : Sprint 1.
- Message de commit recommandé : `refactor: prepare portal views module structure`

### Ticket SPRINT-5.2 — Extraire vues client et checkout
- Type : Refactoring
- Priorité : Moyenne
- Objectif : sortir les vues client/checkout du fichier central.
- Fichiers probables : `backend/apps/portal/views.py`, modules portail, `backend/apps/portal/urls.py`
- Étapes techniques :
  - Déplacer `ClientDashboardView`, listes/détails client, checkout.
  - Préserver noms importés dans `urls.py`.
  - Lancer tests ciblés.
- Critères d’acceptation :
  - Parcours client inchangé.
  - URLs client inchangées.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/ui tests/orders tests/uploads'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
```
- Risques : rupture template context.
- Dépendances : SPRINT-5.1.
- Message de commit recommandé : `refactor: extract client portal views`

### Ticket SPRINT-5.3 — Extraire vues staff commandes et panels
- Type : Refactoring
- Priorité : Moyenne
- Objectif : découper staff dashboard, order detail et panels.
- Fichiers probables : modules portail, `backend/apps/portal/urls.py`, tests UI
- Étapes techniques :
  - Déplacer staff orders.
  - Déplacer panels production/shipping/billing/scan.
  - Garder les permissions existantes.
- Critères d’acceptation :
  - Parcours staff inchangé.
  - Permissions staff inchangées.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/ui tests/production tests/shipping tests/billing'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
```
- Risques : régression HTMX ou permission.
- Dépendances : SPRINT-5.1, idéalement Sprint 3.
- Message de commit recommandé : `refactor: extract staff portal views`

### Ticket SPRINT-5.4 — Extraire presenters/helpers portail
- Type : Refactoring
- Priorité : Faible/Moyenne
- Objectif : sortir `badge_tone`, `status_label`, `_staff_order_upload_rows`.
- Fichiers probables : `backend/apps/portal/presenters.py`, `backend/apps/portal/status.py`, tests UI
- Étapes techniques :
  - Extraire helpers purs.
  - Ajouter tests unitaires si pertinent.
  - Garder rendu identique.
- Critères d’acceptation :
  - Helpers isolés.
  - Pas de changement visuel attendu.
- Commandes Docker de validation :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/ui'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
```
- Risques : contexte template incomplet.
- Dépendances : SPRINT-5.2, SPRINT-5.3.
- Message de commit recommandé : `refactor: extract portal presenters`

Backlog Sprint 5 :

| ID | Titre | Type | Priorité | Effort estimé | Dépendance | Statut |
|---|---|---|---|---|---|---|
| SPRINT-5.1 | Structure modules portail | Refactoring | Moyenne | 1 j | Sprint 1 | À faire |
| SPRINT-5.2 | Extraire client/checkout | Refactoring | Moyenne | 2-3 j | 5.1 | À faire |
| SPRINT-5.3 | Extraire staff/panels | Refactoring | Moyenne | 3-5 j | 5.1, Sprint 3 | À faire |
| SPRINT-5.4 | Extraire presenters/helpers | Refactoring | Faible/Moyenne | 1-2 j | 5.2, 5.3 | À faire |

Livrables :
- `portal/views.py` réduit.
- Modules portail plus lisibles.
- Routes et comportements préservés.
- Tests UI passants.

Définition de Done :
- Refactoring pur, sans changement métier.
- Tests UI et domaines liés passants.
- Aucun formatage global mélangé si non nécessaire.

## Ordre recommandé des sprints

1. Sprint 1 ferme les risques de base : secret Docker, migrations, qualité, audit dépendances.
2. Sprint 2 traite les surfaces d’attaque applicatives les plus concrètes.
3. Sprint 3 stabilise les performances et les transitions métier une fois la base saine.
4. Sprint 4 durcit le runtime Docker avec moins de bruit applicatif.
5. Sprint 5 refactore le portail seulement quand les tests, la sécurité et le déploiement sont plus fiables.

Cet ordre limite les régressions : on ne refactore pas un système dont les migrations, les checks et les risques sécurité critiques ne sont pas encore maîtrisés.

## Commandes globales de validation Docker

Après Sprint 1 :
```bash
docker compose build --no-cache web worker nginx
docker compose up -d db redis web worker nginx
docker compose ps
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
docker compose exec web sh -lc 'cd /app/backend && python manage.py makemigrations --check --dry-run'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest'
docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'
curl --fail http://localhost:8080/healthz/
```

Après Sprint 2 :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/uploads tests/billing tests/accounts'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/uploads backend/apps/billing backend/apps/accounts tests/uploads tests/billing tests/accounts'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

Après Sprint 3 :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/orders tests/ui tests/production'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/orders backend/apps/portal backend/apps/production tests/orders tests/ui tests/production'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

Après Sprint 4 :
```bash
docker compose build --no-cache web worker nginx
docker compose up -d db redis web worker nginx
docker compose ps
docker compose exec web sh -lc 'id && cd /app/backend && python manage.py check'
docker compose exec web sh -lc 'cd /app/backend && python manage.py migrate --plan'
docker compose exec redis redis-cli ping
curl --fail http://localhost:8080/healthz/
```

Après Sprint 5 :
```bash
docker compose run --rm --entrypoint sh web -lc 'cd /app && pytest tests/ui tests/orders tests/uploads tests/production tests/shipping tests/billing'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check backend/apps/portal tests/ui'
docker compose exec web sh -lc 'cd /app/backend && python manage.py check'
curl --fail http://localhost:8080/healthz/
```

## Risques transverses

- Les commandes `ruff`, `pytest`, `pip-audit` dépendent de la réussite du Sprint 1.3 si l’image actuelle ne contient que les dépendances prod.
- Les secrets doivent être tournés si une image contenant `.env` a déjà été poussée.
- Les migrations doivent être validées sur PostgreSQL, pas seulement SQLite.
- La validation upload peut rejeter des fichiers clients existants si les signatures sont trop strictes.
- La pagination peut changer le contrat API attendu par certains consommateurs.
- Le passage non-root peut casser les droits sur médias/statiques.
- Le refactoring portail peut créer des imports circulaires ou des contextes template incomplets.
- Les tests actuels ne remplacent pas un vrai test navigateur complet, surtout pour HTMX.

## Règles d’exécution

- Une PR = un objectif.
- Pas de refactoring mélangé avec sécurité.
- Pas de formatage mélangé avec changements métier.
- Toujours vérifier sous Docker.
- Toujours préserver le comportement existant.
- Si une correction plus large est découverte, la noter dans “À traiter plus tard”.
- Chaque PR doit contenir ses tests ou sa justification si aucun test n’est pertinent.
- Les commandes de validation doivent utiliser `docker compose`.
- Ne pas introduire de service ou dépendance dev dans l’image prod sans décision explicite.
