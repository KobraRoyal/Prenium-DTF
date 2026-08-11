#!/bin/sh
set -eu

umask 077

PROJECT_ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
COMPOSE_FILE=${COMPOSE_FILE:-$PROJECT_ROOT_DIR/docker-compose.prod.yml}
MEDIA_BACKUP_DIR=${MEDIA_BACKUP_DIR:-$PROJECT_ROOT_DIR/data/backups/media}
MEDIA_BACKUP_RETENTION_DAYS=${MEDIA_BACKUP_RETENTION_DAYS:-14}
BACKUP_TIMESTAMP=${BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}
DOCKER_BIN=${DOCKER_BIN:-docker}

case "$MEDIA_BACKUP_RETENTION_DAYS" in
    ''|*[!0-9]*)
        echo "MEDIA_BACKUP_RETENTION_DAYS must be a non-negative integer." >&2
        exit 64
        ;;
esac

case "$BACKUP_TIMESTAMP" in
    ''|*[!0-9TZ]*)
        echo "BACKUP_TIMESTAMP contains unsupported characters." >&2
        exit 64
        ;;
esac

if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Compose file not found: $COMPOSE_FILE" >&2
    exit 66
fi

case "$MEDIA_BACKUP_DIR" in
    ''|'/'|'.'|'..'|"$PROJECT_ROOT_DIR")
        echo "Refusing unsafe MEDIA_BACKUP_DIR: $MEDIA_BACKUP_DIR" >&2
        exit 64
        ;;
esac

mkdir -p "$MEDIA_BACKUP_DIR"
MEDIA_BACKUP_DIR=$(CDPATH= cd -- "$MEDIA_BACKUP_DIR" && pwd)

case "$MEDIA_BACKUP_DIR" in
    '/'|"$PROJECT_ROOT_DIR")
        echo "Refusing unsafe resolved backup directory: $MEDIA_BACKUP_DIR" >&2
        exit 64
        ;;
esac

BACKUP_NAME="prenium-dtf-media-${BACKUP_TIMESTAMP}.tar.gz"
BACKUP_PATH="$MEDIA_BACKUP_DIR/$BACKUP_NAME"
TEMP_PATH="$MEDIA_BACKUP_DIR/.${BACKUP_NAME}.tmp"
CHECKSUM_PATH="${BACKUP_PATH}.sha256"

cleanup() {
    if [ -f "$TEMP_PATH" ]; then
        rm -f -- "$TEMP_PATH"
    fi
}
trap cleanup EXIT HUP INT TERM

"$DOCKER_BIN" compose \
    --project-directory "$PROJECT_ROOT_DIR" \
    -f "$COMPOSE_FILE" \
    run --rm --no-deps --entrypoint sh web -ec \
    'cd /var/app/media && exec tar -czf - .' \
    >"$TEMP_PATH"

if [ ! -s "$TEMP_PATH" ]; then
    echo "Media backup is empty." >&2
    exit 74
fi

tar -tzf "$TEMP_PATH" >/dev/null
mv -- "$TEMP_PATH" "$BACKUP_PATH"

if command -v sha256sum >/dev/null 2>&1; then
    (cd "$MEDIA_BACKUP_DIR" && sha256sum "$BACKUP_NAME") >"$CHECKSUM_PATH"
elif command -v shasum >/dev/null 2>&1; then
    (cd "$MEDIA_BACKUP_DIR" && shasum -a 256 "$BACKUP_NAME") >"$CHECKSUM_PATH"
else
    echo "Neither sha256sum nor shasum is available." >&2
    exit 69
fi

find "$MEDIA_BACKUP_DIR" -type f \
    \( -name 'prenium-dtf-media-*.tar.gz' -o -name 'prenium-dtf-media-*.tar.gz.sha256' \) \
    -mtime "+$MEDIA_BACKUP_RETENTION_DAYS" -exec rm -f {} \;

echo "Media backup verified: $BACKUP_PATH"
echo "Checksum: $CHECKSUM_PATH"
