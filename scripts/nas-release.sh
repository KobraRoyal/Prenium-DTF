#!/bin/sh
# Release NAS — à exécuter sur le Synology (SSH ou terminal Container Manager).
# Depuis /volume1/docker/PreniumDTF après synchronisation du code depuis main.
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -f docker-compose.yml ]; then
  echo "Erreur : docker-compose.yml introuvable dans $ROOT" >&2
  exit 1
fi

if [ -z "${APP_IMAGE_TAG:-}" ]; then
  if command -v git >/dev/null 2>&1 && git -C "$ROOT" rev-parse --short=12 HEAD >/dev/null 2>&1; then
    APP_IMAGE_TAG="$(git -C "$ROOT" rev-parse --short=12 HEAD)"
    APP_REVISION="$(git -C "$ROOT" rev-parse HEAD)"
  else
    APP_IMAGE_TAG="nas-$(date +%Y%m%d%H%M)"
    APP_REVISION="$APP_IMAGE_TAG"
  fi
fi

export APP_IMAGE_TAG
export APP_REVISION="${APP_REVISION:-$APP_IMAGE_TAG}"

COMPOSE="docker compose"
if ! $COMPOSE version >/dev/null 2>&1; then
  COMPOSE="docker-compose"
fi

echo "==> Release Prenium DTF (image: prenium-dtf-backend-prod:${APP_IMAGE_TAG})"
echo "==> Vérification compose"
$COMPOSE config >/dev/null

echo "==> Build web + nginx"
$COMPOSE build web nginx

echo "==> Redémarrage web, worker, beat, nginx"
$COMPOSE up -d web worker beat nginx

echo "==> État des services"
$COMPOSE ps

echo "==> Attente santé web (max ~3 min)"
for _ in $(seq 1 36); do
  if curl -sf --max-time 5 http://127.0.0.1:8080/healthz/ >/dev/null 2>&1; then
    echo "healthz OK"
    curl -sI http://127.0.0.1:8080/static/css/portal.css | head -5
    exit 0
  fi
  sleep 5
done

echo "healthz non OK — consulter : $COMPOSE logs --tail=120 web nginx" >&2
exit 1
