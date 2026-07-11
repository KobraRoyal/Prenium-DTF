#!/bin/sh
set -eu

cd /app/backend

exec gosu app celery -A config beat \
  --loglevel="${CELERY_LOGLEVEL:-info}" \
  --pidfile=/tmp/celerybeat.pid \
  --schedule=/tmp/celerybeat-schedule
