from django.core.cache import caches
from django.db import connections


class HealthcheckService:
    cache_alias = "default"

    def get_payload(self) -> dict[str, object]:
        checks = {
            "database": self._check_database(),
            "cache": self._check_cache(),
        }
        is_healthy = all(checks.values())
        return {
            "status": "ok" if is_healthy else "degraded",
            "checks": checks,
        }

    def is_healthy(self) -> bool:
        payload = self.get_payload()
        return payload["status"] == "ok"

    def _check_database(self) -> bool:
        try:
            with connections["default"].cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            return False
        return True

    def _check_cache(self) -> bool:
        cache = caches[self.cache_alias]
        key = "healthcheck:ping"
        value = "pong"
        try:
            cache.set(key, value, 5)
            return cache.get(key) == value
        except Exception:
            return False
