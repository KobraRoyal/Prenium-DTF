#!/bin/sh
set -eu

cd "${APP_BACKEND_DIR:-/app/backend}"

PIDFILE="${CELERY_BEAT_PIDFILE:-/tmp/celerybeat.pid}"
SCHEDULE_FILE="${CELERY_BEAT_SCHEDULE_FILE:-/tmp/celerybeat-schedule}"

# Docker restart preserves the writable container layer. A PID file left by a
# terminated Beat process would therefore block every subsequent restart with
# exit code 73. Compose already guarantees one Beat process per container, so
# the previous runtime PID file must never be reused.
rm -f "$PIDFILE"

exec gosu app celery -A config beat \
  --loglevel="${CELERY_LOGLEVEL:-info}" \
  --pidfile="$PIDFILE" \
  --schedule="$SCHEDULE_FILE"
