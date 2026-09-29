"""Test settings with production-like PostgreSQL locking and eager task behavior.

Use with ``pytest --ds=config.settings.test_postgres`` against a disposable
PostgreSQL test database. The normal fast suite keeps using SQLite.
"""

from .base import DATABASES as POSTGRES_DATABASES
from .test import *  # noqa: F403

DATABASES = POSTGRES_DATABASES
