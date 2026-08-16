#!/bin/sh
set -eu

cd /app/backend

STATIC_ROOT="${DJANGO_STATIC_ROOT:-/var/app/static}"
MEDIA_ROOT="${DJANGO_MEDIA_ROOT:-/var/app/media}"

mkdir -p "$MEDIA_ROOT" "$STATIC_ROOT"

# Drop stale bytecode left on a persistent volume.
find /app/backend -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find /app/backend -type f -name '*.pyc' -delete 2>/dev/null || true

# Named volumes on Synology often keep root-owned hashed CSS from older runs.
# `chown` can be a no-op there; collectstatic must still overwrite those files.
chmod -R u+rwX,a+rX "$MEDIA_ROOT" "$STATIC_ROOT" 2>/dev/null || true
chown -R app:app "$MEDIA_ROOT" "$STATIC_ROOT" 2>/dev/null || true

gosu app python manage.py migrate --noinput
python manage.py collectstatic --noinput
chmod -R a+rX "$STATIC_ROOT" 2>/dev/null || true
chown -R app:app "$STATIC_ROOT" "$MEDIA_ROOT" 2>/dev/null || true

exec gosu app gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  ${GUNICORN_RELOAD:+--reload}
