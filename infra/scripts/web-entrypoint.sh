#!/bin/sh
set -eu

cd /app/backend

STATIC_ROOT="${DJANGO_STATIC_ROOT:-/var/app/static}"
MEDIA_ROOT="${DJANGO_MEDIA_ROOT:-/var/app/media}"

mkdir -p "$MEDIA_ROOT" "$STATIC_ROOT"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}"
