#!/bin/sh
set -eu

cd /app/backend

MEDIA_ROOT="${DJANGO_MEDIA_ROOT:-/var/app/media}"

mkdir -p "$MEDIA_ROOT"
chown -R app:app "$MEDIA_ROOT"

exec gosu app celery -A config worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" \
  --concurrency="${CELERY_WORKER_CONCURRENCY:-2}"
