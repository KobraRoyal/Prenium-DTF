#!/bin/sh
set -eu

cd /app/backend

exec celery -A config worker \
  --loglevel="${CELERY_LOGLEVEL:-info}" \
  --uid="${CELERY_UID:-nobody}" \
  --gid="${CELERY_GID:-nogroup}"
