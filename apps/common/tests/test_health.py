import pytest
from django.core.cache import cache
from django.db import connection
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_endpoint_returns_liveness_payload() -> None:
    response = APIClient().get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"service": "medcore-backend", "status": "ok"}


@pytest.mark.django_db
def test_openapi_schema_contains_health_endpoint() -> None:
    response = APIClient().get("/api/v1/schema/")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/vnd.oai.openapi")
    assert b"/api/v1/health/:" in response.content


class _HealthyCursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query):
        assert query == "SELECT 1"


def test_liveness_does_not_touch_dependencies(monkeypatch) -> None:
    def fail():
        raise AssertionError("liveness must not check dependencies")

    monkeypatch.setattr(connection, "cursor", fail)
    monkeypatch.setattr(cache, "get", fail)

    response = APIClient().get("/api/v1/health/live/")

    assert response.status_code == 200
    assert response.json() == {"service": "medcore-backend", "status": "ok"}


def test_readiness_returns_ok_when_dependencies_are_healthy(monkeypatch) -> None:
    monkeypatch.setattr(connection, "cursor", lambda: _HealthyCursor())
    monkeypatch.setattr(cache, "get", lambda key: None)

    response = APIClient().get("/api/v1/health/ready/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "medcore-backend",
        "status": "ok",
        "checks": {"database": "ok", "cache": "ok"},
    }


@pytest.mark.parametrize("failed_check", ["database", "cache"])
def test_readiness_returns_503_for_one_failed_dependency(
    monkeypatch, failed_check
) -> None:
    monkeypatch.setattr(connection, "cursor", lambda: _HealthyCursor())
    monkeypatch.setattr(cache, "get", lambda key: None)
    if failed_check == "database":
        monkeypatch.setattr(
            connection,
            "cursor",
            lambda: (_ for _ in ()).throw(RuntimeError("database down")),
        )
    else:
        monkeypatch.setattr(
            cache,
            "get",
            lambda key: (_ for _ in ()).throw(RuntimeError("cache down")),
        )

    response = APIClient().get("/api/v1/health/ready/")

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"][failed_check] == "unavailable"
    other_check = "cache" if failed_check == "database" else "database"
    assert response.json()["checks"][other_check] == "ok"


@pytest.mark.django_db
def test_legacy_health_endpoint_remains_liveness_compatible() -> None:
    client = APIClient()

    live = client.get("/api/v1/health/")

    assert live.status_code == 200
    assert live.json() == {"service": "medcore-backend", "status": "ok"}
