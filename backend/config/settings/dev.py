from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "0.0.0.0"]))  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
