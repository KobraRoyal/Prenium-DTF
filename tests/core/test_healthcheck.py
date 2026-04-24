import pytest
from apps.core.tasks import ping_task


@pytest.mark.django_db
def test_healthcheck_endpoint_returns_ok(client):
    response = client.get("/healthz/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["database"] is True
    assert payload["checks"]["cache"] is True


def test_ping_task_returns_pong():
    result = ping_task.delay()

    assert result.get(timeout=1) == "pong"
