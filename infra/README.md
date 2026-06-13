# Infra

Ce dossier regroupe la configuration Docker, Nginx et les scripts runtime.

## Compose local vs production

Le projet distingue maintenant deux usages :

- `docker-compose.yml` : stack locale de développement. `web` et `worker` utilisent la cible d’image `dev` et montent le code source hôte dans `/app`.
- `docker-compose.prod.yml` : stack autonome orientée production. `web` et `worker` utilisent la cible d’image `prod` et n’embarquent pas le bind mount `.:/app`.

Exemples :

```bash
docker compose up -d db redis web worker nginx
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build web worker
```

## Image backend Docker

Le Dockerfile backend expose deux cibles principales :

- `dev` : pour le local, avec `pytest`, `ruff`, `pre-commit` et `pip-audit`.
- `prod` : runtime applicatif sans outillage de développement.

Commandes qualité sous Docker Compose local :

```bash
docker compose build web worker
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && ruff format --check .'
docker compose run --rm --entrypoint sh web -lc 'cd /app && PYTHONPATH=/app/backend pytest'
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

## Runbook de release Docker

### Pré-check release

Avant tout déploiement orienté production :

```bash
docker compose -f docker-compose.prod.yml config
docker compose -f docker-compose.prod.yml build web worker nginx
docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py check'
docker compose -f docker-compose.prod.yml run --rm --no-deps --entrypoint sh web -lc 'cd /app/backend && python manage.py migrate --plan'
```

Attendus :

- la configuration Compose est résolue sans erreur ;
- les images `web` et `worker` buildent sur la cible `prod` ;
- `manage.py check` ne remonte aucune anomalie ;
- `migrate --plan` est compris et acceptable avant mise en ligne.

### Séquence de déploiement simple

Pour un environnement simple sans orchestration avancée :

```bash
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml up -d web worker nginx
docker compose -f docker-compose.prod.yml ps
curl --fail --silent --show-error http://localhost:8080/healthz/
```

Points de vigilance :

- ne pas lancer plusieurs réplicas `web` tant que `migrate` reste exécuté au démarrage ;
- vérifier la santé HTTP après redémarrage ;
- considérer Redis comme jetable pour cache/broker, pas comme stockage durable.

### Repli minimal en cas d’échec

Si le déploiement échoue après rebuild :

```bash
docker compose -f docker-compose.prod.yml logs --tail=200 web
docker compose -f docker-compose.prod.yml logs --tail=200 worker
docker compose -f docker-compose.prod.yml ps
```

Règles de rollback :

- si l’échec est avant migration effective, redémarrer avec la dernière image connue saine ;
- si une migration destructive a été appliquée, ne pas improviser un rollback applicatif seul ;
- traiter le rollback comme un couple image + schéma + données, avec sauvegarde PostgreSQL valide ;
- si Redis est perdu pendant l’opération, assumer la perte du cache et des tâches non consommées.
