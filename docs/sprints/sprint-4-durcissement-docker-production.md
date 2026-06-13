# Sprint 4 — Durcissement Docker production

## Ticket SPRINT-4.1 — Préparer runtime web non-root

## Objectif

Éviter l’exécution effective des services Django/Celery en root dans le conteneur, tout en gardant un bootstrap compatible avec les volumes Docker persistants.

## Fichiers modifiés

- `infra/docker/backend/Dockerfile`
- `infra/scripts/web-entrypoint.sh`
- `infra/scripts/worker-entrypoint.sh`
- `docs/sprints/sprint-4-durcissement-docker-production.md`

## Résumé technique

L’image backend crée désormais un utilisateur système `app` dédié, propriétaire de `/app` et `/var/app`.

Le bootstrap conteneur reste root uniquement pour reprendre les droits sur les volumes montés (`/var/app/static`, `/var/app/media`), puis `web` et `worker` s’exécutent via `gosu app`.

Cela corrige le cas concret où `collectstatic` échoue sur un volume nommé déjà peuplé avec des fichiers root hérités d’un runtime précédent.

## Commandes Docker de validation

```bash
docker compose build --no-cache web worker
docker compose up -d db redis web worker nginx
docker compose exec web sh -lc 'id && cd /app/backend && python manage.py check'
docker compose ps
curl --fail http://localhost:8080/healthz/
```

## Résultat attendu

- Les processus applicatifs `gunicorn` et `celery` s’exécutent en non-root (`app`).
- `manage.py check` reste OK.
- Le stack reste sain après rebuild.

## Résultats de validation observés

- `docker compose build --no-cache web worker` : OK
- `docker compose up -d db redis web worker nginx` : OK
- `docker compose ps` : `web`, `worker`, `db`, `redis`, `nginx` sains
- `docker compose exec web sh -lc 'cd /app/backend && python manage.py check'` : OK
- vérification du PID 1 dans `web` via `/proc/1/status` : utilisateur `app`
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK

## Risques restants

- Le bootstrap root reste nécessaire tant que des volumes persistants partagent des fichiers créés par d’anciens conteneurs.
- Le lot ne sépare pas encore complètement les modes dev et prod.

## Éléments reportés

- Clarification dev/prod Compose.
- Documentation Redis non persistant.
- Documentation migrations au démarrage.

## Message de commit recommandé

```text
security: run django and celery as non-root after volume bootstrap
```

## Ticket SPRINT-4.2 — Clarifier la séparation Docker dev/prod

## Objectif

Rendre explicite l’usage local vs production de Docker Compose, sans casser la stack locale existante.

## Fichiers modifiés

- `docker-compose.prod.yml`
- `infra/README.md`
- `docs/sprints/sprint-4-durcissement-docker-production.md`

## Résumé technique

Un fichier `docker-compose.prod.yml` autonome a été ajouté pour construire `web` et `worker` sur la cible d’image `prod`, sans bind mount du code source hôte.

La documentation infra précise désormais :

- comment combiner `docker-compose.yml` et `docker-compose.prod.yml` ;
- que Redis n’est pas persistant dans la configuration actuelle ;
- que `migrate` et `collectstatic` sont lancés automatiquement au démarrage du service `web`, avec les implications opérationnelles associées.

## Commandes Docker de validation

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build web worker
docker compose -f docker-compose.prod.yml run --rm --entrypoint sh web -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- L’override production est valide.
- `web` et `worker` peuvent être buildés sur la cible `prod`.
- La documentation d’exploitation explicite les limites actuelles de Redis et des migrations au démarrage.

## Risques restants

- Le fichier `docker-compose.prod.yml` ne traite pas encore la politique de secrets, de backup ou d’orchestration multi-réplicas.
- Le lancement automatique des migrations reste un compromis acceptable pour un déploiement simple, mais pas un mode release avancé.

## Éléments reportés

- Runbook complet de déploiement et rollback.
- Politique de persistance Redis ou backend de résultats Celery dédié.
- Séparation plus stricte des variables d’environnement dev/prod.

## Résultats de validation observés

- `docker compose -f docker-compose.prod.yml config` : OK
- `docker compose -f docker-compose.prod.yml build web worker` : OK
- `docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py check'` : OK
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK
- la configuration résolue de `web` sous `docker-compose.prod.yml` ne monte plus `.:/app`

## Message de commit recommandé

```text
devops: add production compose override and ops notes
```

## Ticket SPRINT-4.3 — Formaliser le runbook release/rollback

## Objectif

Documenter une procédure minimale de release Docker et de repli, cohérente avec les contraintes actuelles du projet.

## Fichiers modifiés

- `infra/README.md`
- `docs/sprints/sprint-4-durcissement-docker-production.md`

## Résumé technique

La documentation infra couvre désormais :

- les pré-checks release Docker Compose prod ;
- la séquence de déploiement simple ;
- les contrôles santé post-déploiement ;
- les règles minimales de rollback autour du triplet image / schéma / données.

Le ticket reste documentaire : aucun comportement runtime n’est modifié.

## Commandes Docker de validation

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py migrate --plan'
docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py check'
curl --fail --silent --show-error http://localhost:8080/healthz/
```

## Résultat attendu

- Le runbook de release est documenté dans le dépôt.
- Les commandes de pré-check et de contrôle post-déploiement sont explicites.
- Les limites actuelles sur rollback et Redis sont clairement posées.

## Risques restants

- Aucun mécanisme automatisé de rollback n’est introduit.
- La stratégie reste adaptée à un déploiement simple, pas à une plateforme multi-instance.

## Éléments reportés

- Sauvegarde/restauration PostgreSQL détaillée.
- Politique de rotation de secrets en production.
- Procédure de release zero-downtime.

## Résultats de validation observés

- `docker compose -f docker-compose.prod.yml config` : OK
- `docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py migrate --plan'` : OK, aucune migration planifiée
- `docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py check'` : OK
- `curl --fail --silent --show-error http://localhost:8080/healthz/` : OK

## Message de commit recommandé

```text
docs: add docker release and rollback runbook
```
