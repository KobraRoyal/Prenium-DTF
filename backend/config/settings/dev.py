import os

from .base import *  # noqa: F403

# Respecte DJANGO_DEBUG (.env) pour prévisualiser les pages d’erreur custom (404).
# Défaut True en local si la variable est absente.
DEBUG = env_bool("DJANGO_DEBUG", True)  # noqa: F405
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "0.0.0.0"]))  # noqa: F405
EMAIL_BACKEND = os.environ.get(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
