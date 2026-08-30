import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Docker Compose injecte souvent config.settings.dev ; forcer le module de test
# sauf si CI (ou un appel explicite) impose déjà un autre module non-dev.
_current_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
if _current_settings in ("", "config.settings.dev"):
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_PASSWORD", "test-password")

import pytest

CATALOG_SEED_CODES = ("seed-dtf-meter", "seed-file-prep")


@pytest.fixture(autouse=True)
def isolate_catalog_seed_services(db):
  """Les services seedés par migration ne doivent pas polluer les fixtures de test."""
  from apps.catalog.models import CatalogService

  CatalogService.objects.filter(code__in=CATALOG_SEED_CODES).delete()
