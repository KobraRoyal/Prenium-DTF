# Infra

Ce dossier regroupe la configuration Docker, Nginx et les scripts runtime.

## Compose local vs production

Le projet distingue maintenant deux usages :

- `docker-compose.yml` : stack locale de développement. `web`, `worker` et `beat` utilisent la cible d’image `dev` et montent le code source hôte dans `/app`.
- `docker-compose.prod.yml` : stack autonome orientée production. `web`, `worker` et `beat` utilisent la cible d’image `prod` et n’embarquent pas le bind mount `.:/app`.
- la stack production force `DJANGO_SETTINGS_MODULE=config.settings.prod`, même si le `.env` local indique les settings de développement.

Exemples :

```bash
docker compose up -d db redis web worker beat nginx
docker compose -f docker-compose.prod.yml config
APP_IMAGE_TAG="$(git rev-parse --short=12 HEAD)" \
APP_REVISION="$(git rev-parse HEAD)" \
docker compose -f docker-compose.prod.yml build web nginx
```

`web`, `worker` et `beat` utilisent obligatoirement la même image backend. Une release construit
donc `web` une seule fois, avec un tag immuable dérivé du SHA Git, puis démarre les trois services
avec ce même `APP_IMAGE_TAG`.

## Image backend Docker

Le Dockerfile backend expose deux cibles principales :

- `dev` : pour le local, avec `pytest`, `ruff`, `pre-commit` et `pip-audit`.
- `prod` : runtime applicatif sans outillage de développement.

Commandes qualité sous Docker Compose local :

```bash
docker compose build web
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest --cov --cov-report=term-missing'
docker compose run --rm --entrypoint sh web -lc 'cd /app/backend && pip-audit -r requirements/prod.txt'
```

## Notes d’exploitation

### Redis

Le service Redis est lancé avec :

```text
redis-server --save "" --appendonly no
```

Cela convient pour le cache Django et le broker/résultat Celery, mais pas pour une persistance métier. La perte du conteneur Redis efface donc :

- le cache applicatif ;
- les résultats Celery stockés dans Redis ;
- les messages en file encore non consommés.

### Migrations au démarrage

`infra/scripts/web-entrypoint.sh` lance automatiquement :

```text
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

Ce mode reste acceptable pour le local et un environnement simple, mais il implique en production :

- une discipline stricte sur l’ordre de déploiement ;
- une vérification préalable avec `python manage.py migrate --plan` ;
- un plan de rollback explicite si une migration échoue ;
- l’absence de montée concurrente incontrôlée de plusieurs réplicas `web`.

### Garde-fous production

Les settings `config.settings.prod` refusent de démarrer si :

- `DJANGO_SECRET_KEY` n’est pas suffisamment longue et aléatoire ;
- SMTP TLS et SSL sont activés simultanément ;
- les emails transactionnels sont actifs avec un hôte SMTP vide ou `localhost`.

Pour un environnement sans SMTP, définir explicitement `TRANSACTIONAL_EMAILS_ENABLED=False`.

## Sauvegardes et restauration

### Politique minimale

- PostgreSQL et les médias sont sauvegardés séparément chaque nuit.
- Les archives sont écrites hors des volumes Docker applicatifs, dans un partage NAS lui-même
  répliqué par Hyper Backup ou une solution équivalente.
- La rétention locale par défaut est de 14 jours ; la rétention distante doit conserver au moins
  une sauvegarde hebdomadaire sur 8 semaines.
- Une archive n'est publiée qu'après validation de sa structure et création de son checksum SHA-256.
- Un test de restauration isolé est réalisé mensuellement et après toute évolution majeure du
  schéma ou des scripts de sauvegarde.

Le planificateur DSM doit exporter les chemins et rétentions suivants ; les scripts ne chargent pas
automatiquement `.env`. Des chemins NAS absolus sont recommandés :

```dotenv
POSTGRES_BACKUP_DIR=/volume1/backups/prenium-dtf/postgres
POSTGRES_BACKUP_RETENTION_DAYS=14
MEDIA_BACKUP_DIR=/volume1/backups/prenium-dtf/media
MEDIA_BACKUP_RETENTION_DAYS=14
```

Ne jamais placer `POSTGRES_BACKUP_DIR` ou `MEDIA_BACKUP_DIR` dans `postgres_data`, `django_media`,
la racine du dépôt ou `/`.

### Exécution quotidienne

Depuis la racine du dépôt, avec la stack déjà démarrée :

```bash
infra/scripts/backup-postgres.sh
APP_IMAGE_TAG="$(git rev-parse --short=12 HEAD)" infra/scripts/backup-media.sh
```

Le script PostgreSQL utilise un dump custom sans propriétaire ni privilèges, puis exécute
`pg_restore --list`. Le script médias monte le volume `django_media`, génère une archive `tar.gz`
et la relit avant publication. Les deux scripts refusent les répertoires dangereux, utilisent des
fichiers temporaires et créent un manifeste `.sha256`.

Le planificateur de tâches Synology doit exécuter ces deux commandes avec l'utilisateur dédié au
projet. Une alerte doit être déclenchée sur tout code de sortie non nul et sur l'absence d'une
archive récente.

### Vérification d'une archive

```bash
cd /volume1/backups/prenium-dtf/postgres
sha256sum -c prenium-dtf-YYYYMMDDTHHMMSSZ.dump.sha256
pg_restore --list prenium-dtf-YYYYMMDDTHHMMSSZ.dump >/dev/null

cd /volume1/backups/prenium-dtf/media
sha256sum -c prenium-dtf-media-YYYYMMDDTHHMMSSZ.tar.gz.sha256
tar -tzf prenium-dtf-media-YYYYMMDDTHHMMSSZ.tar.gz >/dev/null
```

### Test de restauration isolé

Ne jamais restaurer directement dans la base active. Créer une instance PostgreSQL 16 jetable,
restaurer le dump avec `--exit-on-error --no-owner --no-privileges`, vérifier les tables et les
migrations, puis seulement préparer une procédure de bascule :

```bash
docker volume create prenium-dtf-restore-drill
docker run -d --name prenium-dtf-restore-drill \
  -e POSTGRES_DB=restore_drill \
  -e POSTGRES_USER=restore_drill \
  -e POSTGRES_PASSWORD=restore-drill-only \
  -v prenium-dtf-restore-drill:/var/lib/postgresql/data \
  postgres:16-alpine

docker exec prenium-dtf-restore-drill pg_isready -U restore_drill -d restore_drill
docker exec -i prenium-dtf-restore-drill \
  pg_restore --exit-on-error --no-owner --no-privileges \
  -U restore_drill -d restore_drill \
  < /volume1/backups/prenium-dtf/postgres/prenium-dtf-YYYYMMDDTHHMMSSZ.dump
docker exec prenium-dtf-restore-drill \
  psql -U restore_drill -d restore_drill -tAc 'SELECT count(*) FROM django_migrations;'
```

Après validation, supprimer uniquement le conteneur et le volume jetables explicitement nommés.
Pour une restauration réelle : mettre l'application en maintenance, conserver une sauvegarde de
l'état courant, restaurer d'abord PostgreSQL puis les médias correspondant au même créneau, exécuter
les checks Django et effectuer la recette sécurité multi-tenant avant réouverture.

### Rotation des secrets

Une exclusion `.dockerignore` protège les futurs builds, mais ne révoque jamais un secret déjà
affiché, copié, sauvegardé ou intégré à une ancienne image. Après toute exposition, faire tourner au
minimum la clé Django, les identifiants PostgreSQL, SMTP, Drive, Sendcloud, PayPal et Stripe concernés,
puis reconstruire les images et invalider les anciens jetons côté fournisseur.

## Runbook de release Docker

### Pré-check release

Avant tout déploiement orienté production :

```bash
docker compose -f docker-compose.prod.yml config
APP_IMAGE_TAG="$(git rev-parse --short=12 HEAD)" \
APP_REVISION="$(git rev-parse HEAD)" \
docker compose -f docker-compose.prod.yml build web nginx
docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py check --deploy --fail-level WARNING'
docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py migrate --plan'
```

Attendus :

- la configuration Compose est résolue sans erreur ;
- l'image backend commune et l'image Nginx buildent sans code source monté depuis l'hôte ;
- `manage.py check --deploy` ne remonte aucune anomalie ;
- `migrate --plan` est compris et acceptable avant mise en ligne.

### Séquence de déploiement simple

Pour un environnement simple sans orchestration avancée :

```bash
export APP_IMAGE_TAG="$(git rev-parse --short=12 HEAD)"
export APP_REVISION="$(git rev-parse HEAD)"
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml up -d web worker beat nginx
docker compose -f docker-compose.prod.yml ps
curl --fail --silent --show-error \
  --header 'X-Forwarded-Proto: https' \
  http://localhost:8080/healthz/
```

Points de vigilance :

- ne pas lancer plusieurs réplicas `web` tant que `migrate` reste exécuté au démarrage ;
- vérifier que `web`, `worker` et `beat` référencent le même identifiant d'image ;
- vérifier la santé via le domaine HTTPS public ; l'en-tête ci-dessus simule uniquement le reverse
  proxy lors d'un test interne au NAS ;
- considérer Redis comme jetable pour cache/broker, pas comme stockage durable.

### Repli minimal en cas d’échec

Si le déploiement échoue après rebuild :

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 web
docker compose -f docker-compose.prod.yml logs --tail=200 worker
docker compose -f docker-compose.prod.yml logs --tail=200 beat
docker compose -f docker-compose.prod.yml ps
```

Règles de rollback :

- si l’échec est avant migration effective, redémarrer avec la dernière image connue saine ;
- si une migration destructive a été appliquée, ne pas improviser un rollback applicatif seul ;
- traiter le rollback comme un couple image + schéma + données, avec sauvegarde PostgreSQL valide ;
- si Redis est perdu pendant l’opération, assumer la perte du cache et des tâches non consommées.
