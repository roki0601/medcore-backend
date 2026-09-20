import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_request_data_too_big_uses_api_error_envelope(settings) -> None:
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 16

    response = APIClient().post(
        "/api/v1/auth/telegram/",
        data="x" * 32,
        content_type="application/json",
        HTTP_HOST="localhost",
    )

    assert response.status_code == 400
    assert response["Content-Type"].startswith("application/json")
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "detail": "Request body is too large.",
        "fields": {},
    }
