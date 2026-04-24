import tempfile
from pathlib import Path

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(BASE_DIR) / "var" / "test.sqlite3",  # noqa: F405
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "prenium-dtf-test-cache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
STATIC_ROOT = Path(tempfile.gettempdir()) / "prenium-dtf-test-static"
MEDIA_ROOT = Path(tempfile.gettempdir()) / "prenium-dtf-test-media"
