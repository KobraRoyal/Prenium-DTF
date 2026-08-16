# Sprint 39 — Contrat de production NAS

Date : 2026-08-16

## Objectif

Aligner le runtime DS218+ (Container Manager, `smb://KobraNas/docker/PreniumDTF`)
sur `docker-compose.prod.yml`, pour que rebuild, statiques et reverse proxy
restent sains sans bind-mounts de code.

## Incident du 16 août (leçons)

- `migrate` lancé à la main pendant l’entrypoint → `UniqueViolation` sur
  `auth_permission` (course `post_migrate`).
- `collectstatic` en user `app` sur un volume encore possédé par `root`.
- Nginx recréé trop tard / IP `web` figée → HTTP 502 alors que Gunicorn écoutait.
- Healthcheck nginx limité à `/static/css/app.css` → nginx « healthy » en 502.
- Dossier hôte `infra/nginx/prenium-static` figé → page Atelier sans CSS.
- Image prod sans `backend/templates` dans l’étape CSS Tailwind → purge de
  `@layer components` (`product-shell`) → `/staff/` garde le fond sombre
  `body.landing-saas` alors que `portal.css` répond 200.

## Livré dans le dépôt

- `docker-compose.prod.yml` est le contrat NAS : projet `preniumdtf`, image
  backend unique taguée, volumes nommés uniquement, nginx dépend de `web`
  healthy, healthcheck nginx = `/healthz/` **et** CSS.
- Nginx résout `web` via le DNS Docker (`resolver 127.0.0.11`, `valid=30s`).
- Entrypoint : `migrate` en user `app`, `collectstatic` en root, Gunicorn en
  `app`. Plus de tar `static_src` vers le volume.
- Étape CSS Docker : `COPY backend/templates` avant `npm run build:assets`.
- `entries/portal.css` : fond Atelier `#f7f5f0` hors `@layer` pour battre
  `body.landing-saas`.
- Tests de contrat dans `tests/core/test_deployment_contracts.py`.

## Hors périmètre (actions environnement)

Ces points restent manuels sur DSM / GitHub / fournisseurs :

- [ ] rotation des secrets exposés (R-029) ;
- [ ] planification DSM de `backup-postgres.sh` et `backup-media.sh` + Hyper Backup (R-030) ;
- [ ] checks CI obligatoires sur `main` (R-031) ;
- [ ] recette SMTP, Drive, Sendcloud, PayPal, Stripe en conditions réelles.

## Séquence NAS (Container Manager / SSH)

Ne pas toucher `.env`, `data/`, ni les volumes `postgres_data` / `django_media`.

```bash
cd /volume1/docker/PreniumDTF
# Le fichier docker-compose.yml du partage DOIT être le contrat prod.
sudo docker-compose build web nginx
sudo docker-compose up -d web worker beat nginx
sudo docker-compose ps
curl --fail --silent --show-error http://127.0.0.1:8080/healthz/
curl -sI http://127.0.0.1:8080/static/css/portal.css | head -5
# Contrôle visuel : /staff/ doit être fond crème, pas noir landing.
# Content-Length portal.css attendu ~300k (pas ~107k).
```

Règles :

- ne pas `exec ... migrate` pendant le `up` : l’entrypoint s’en charge ;
- après un rebuild de `web`, toujours recréer `nginx` (`up -d nginx`) ;
- attendre `web` **healthy** (~2 min) avant de juger un 502 ;
- rechargement navigateur forcé après publication des CSS hashés.

## Validation dépôt

- [x] contrats Compose / Nginx / entrypoint
- [x] rebuild NAS `web` + `nginx` sans bind-mount
- [x] `healthz` 200 et `portal.css` 200 (`Content-Length` 331571)
- [x] page `/staff/` stylée après hard refresh (fond crème Atelier)
