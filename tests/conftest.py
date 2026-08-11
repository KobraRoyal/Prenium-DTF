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
