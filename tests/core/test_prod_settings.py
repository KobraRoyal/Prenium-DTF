import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]


def _prod_env(**overrides: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "DJANGO_SECRET_KEY": "audit-prod-secret-" + "a8F4zP9qK2mN7xR5" * 4,
            "DJANGO_ALLOWED_HOSTS": "example.com",
            "DJANGO_EMAIL_HOST": "smtp.example.com",
            "POSTGRES_PASSWORD": "test-only-password",
            "PYTHONPATH": str(ROOT_DIR / "backend"),
        }
    )
    env.update(overrides)
    return env


def _load_prod_settings(
    expression: str = "settings.DEBUG",
    **overrides: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", f"from django.conf import settings; print({expression})"],
        cwd=ROOT_DIR,
        env=_prod_env(**overrides),
        check=False,
        capture_output=True,
        text=True,
    )


def test_prod_settings_accept_complete_secure_configuration():
    result = _load_prod_settings()

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_prod_settings_keep_https_enabled_despite_environment_override():
    result = _load_prod_settings(
        "settings.SECURE_SSL_REDIRECT",
        DJANGO_SECURE_SSL_REDIRECT="False",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_prod_settings_reject_weak_secret_key():
    result = _load_prod_settings(DJANGO_SECRET_KEY="change-me")

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY must be long and random" in result.stderr


def test_prod_settings_require_smtp_when_transactional_email_is_enabled():
    result = _load_prod_settings(DJANGO_EMAIL_HOST="localhost")

    assert result.returncode != 0
    assert "DJANGO_EMAIL_HOST must be configured" in result.stderr
