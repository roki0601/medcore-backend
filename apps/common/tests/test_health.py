import pytest
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
