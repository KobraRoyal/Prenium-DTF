#!/bin/sh
set -eu

cd /app/backend

STATIC_ROOT="${DJANGO_STATIC_ROOT:-/var/app/static}"
MEDIA_ROOT="${DJANGO_MEDIA_ROOT:-/var/app/media}"

mkdir -p "$MEDIA_ROOT" "$STATIC_ROOT"
chown -R app:app "$MEDIA_ROOT" "$STATIC_ROOT" 2>/dev/null || true

# Drop stale bytecode so bind-mounted .py (urls.py, settings) are actually loaded.
find /app/backend -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find /app/backend -type f -name '*.pyc' -delete 2>/dev/null || true

# Seed shared static volume from bind-mounted static_src (authoritative on NAS).
if [ -d /app/backend/static_src ]; then
  # Avoid cp -a (SMB xattrs can fail under set -e on Synology).
  tar -C /app/backend/static_src --exclude='.DS_Store' -cf - . \
    | tar -C "$STATIC_ROOT" -xf -
  chmod -R a+rX "$STATIC_ROOT" 2>/dev/null || true
  chown -R app:app "$STATIC_ROOT" 2>/dev/null || true
fi

gosu app python manage.py migrate --noinput
gosu app python manage.py collectstatic --noinput

exec gosu app gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  ${GUNICORN_RELOAD:+--reload}
