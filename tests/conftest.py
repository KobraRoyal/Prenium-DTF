import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
os.environ.setdefault("DJANGO_SECRET_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_PASSWORD", "test-password")
