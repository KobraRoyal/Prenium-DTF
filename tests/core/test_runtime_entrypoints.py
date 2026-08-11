import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def test_beat_entrypoint_removes_stale_pid_before_start(tmp_path):
    backend_dir = tmp_path / "backend"
    bin_dir = tmp_path / "bin"
    backend_dir.mkdir()
    bin_dir.mkdir()

    pidfile = tmp_path / "celerybeat.pid"
    schedule_file = tmp_path / "celerybeat-schedule"
    args_file = tmp_path / "celery-args"
    pidfile.write_text("1\n")

    gosu = bin_dir / "gosu"
    gosu.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    gosu.chmod(0o755)

    celery = bin_dir / "celery"
    celery.write_text(
        "#!/bin/sh\n"
        'test ! -e "$CELERY_BEAT_PIDFILE" || exit 91\n'
        'printf "%s\\n" "$@" > "$CELERY_ARGS_FILE"\n'
    )
    celery.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "APP_BACKEND_DIR": str(backend_dir),
            "CELERY_BEAT_PIDFILE": str(pidfile),
            "CELERY_BEAT_SCHEDULE_FILE": str(schedule_file),
            "CELERY_ARGS_FILE": str(args_file),
        }
    )

    entrypoint = ROOT_DIR / "infra" / "scripts" / "beat-entrypoint.sh"
    result = subprocess.run(
        ["sh", str(entrypoint)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not pidfile.exists()
    assert f"--pidfile={pidfile}" in args_file.read_text().splitlines()
    assert f"--schedule={schedule_file}" in args_file.read_text().splitlines()


def test_postgres_backup_is_verified_before_publication(tmp_path):
    backup_dir = tmp_path / "backups"
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}\n")

    docker = tmp_path / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *pg_dump*) printf 'PGDMP verified test archive' ;;\n"
        "  *pg_restore*) grep -q '^PGDMP' ;;\n"
        "  *) exit 92 ;;\n"
        "esac\n"
    )
    docker.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "COMPOSE_FILE": str(compose_file),
            "POSTGRES_BACKUP_DIR": str(backup_dir),
            "POSTGRES_BACKUP_RETENTION_DAYS": "30",
            "BACKUP_TIMESTAMP": "20260811T120000Z",
            "DOCKER_BIN": str(docker),
        }
    )

    script = ROOT_DIR / "infra" / "scripts" / "backup-postgres.sh"
    result = subprocess.run(
        ["sh", str(script)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    backup = backup_dir / "prenium-dtf-20260811T120000Z.dump"
    checksum = backup.with_suffix(".dump.sha256")
    assert result.returncode == 0, result.stderr
    assert backup.read_bytes() == b"PGDMP verified test archive"
    assert backup.name in checksum.read_text()
    assert not list(backup_dir.glob("*.tmp"))


def test_postgres_backup_refuses_unsafe_directory(tmp_path):
    compose_file = tmp_path / "compose.yml"
    compose_file.write_text("services: {}\n")
    env = os.environ.copy()
    env.update(
        {
            "COMPOSE_FILE": str(compose_file),
            "POSTGRES_BACKUP_DIR": "/",
            "BACKUP_TIMESTAMP": "20260811T120000Z",
        }
    )

    script = ROOT_DIR / "infra" / "scripts" / "backup-postgres.sh"
    result = subprocess.run(
        ["sh", str(script)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 64
    assert "Refusing unsafe POSTGRES_BACKUP_DIR" in result.stderr


def test_media_backup_is_verified_before_publication(tmp_path):
    backup_dir = tmp_path / "backups"
    media_source = tmp_path / "media"
    compose_file = tmp_path / "compose.yml"
    media_source.mkdir()
    (media_source / "asset.txt").write_text("production asset")
    compose_file.write_text("services: {}\n")

    docker = tmp_path / "docker"
    docker.write_text('#!/bin/sh\nexec tar -czf - -C "$FAKE_MEDIA_SOURCE" .\n')
    docker.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "COMPOSE_FILE": str(compose_file),
            "MEDIA_BACKUP_DIR": str(backup_dir),
            "MEDIA_BACKUP_RETENTION_DAYS": "30",
            "BACKUP_TIMESTAMP": "20260811T120000Z",
            "DOCKER_BIN": str(docker),
            "FAKE_MEDIA_SOURCE": str(media_source),
        }
    )

    script = ROOT_DIR / "infra" / "scripts" / "backup-media.sh"
    result = subprocess.run(
        ["sh", str(script)],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    backup = backup_dir / "prenium-dtf-media-20260811T120000Z.tar.gz"
    checksum = backup.with_suffix(".gz.sha256")
    assert result.returncode == 0, result.stderr
    assert backup.stat().st_size > 0
    assert backup.name in checksum.read_text()
    assert not list(backup_dir.glob("*.tmp"))
