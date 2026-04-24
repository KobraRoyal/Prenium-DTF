from celery.schedules import crontab

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "0.0.0.0"]))  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

CELERY_BEAT_SCHEDULE = {
    "shipping-sync-stale-tracking": {
        "task": "shipping.sync_stale_shipments_tracking",
        "schedule": crontab(minute="*/30"),
    },
}
