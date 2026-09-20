from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.users.models import RefreshSession

from .helpers import TEST_BOT_TOKEN, csrf_headers, telegram_payload

User = get_user_model()


@pytest.fixture(autouse=True)
def configure_telegram(settings):
    settings.TELEGRAM_BOT_TOKEN = TEST_BOT_TOKEN
    settings.TELEGRAM_AUTH_MAX_AGE = 86400
    settings.TELEGRAM_AUTH_FUTURE_SKEW = 60


@pytest.fixture
def client() -> APIClient:
    return APIClient(enforce_csrf_checks=True)


def login(client: APIClient, payload: dict[str, object]):
    headers = csrf_headers(client)
    response = client.post(
        "/api/v1/auth/telegram/",
        payload,
        format="json",
        **headers,
    )
    assert response.status_code == 200, response.content
    return response


@pytest.mark.django_db
def test_telegram_login_creates_user_and_sets_http_only_refresh_cookie(client):
    response = login(client, telegram_payload())

    body = response.json()
    assert body["access_token"]
    assert body["expires_in"] == 900
    assert body["user"]["has_telegram"] is True
    assert "telegram_id" not in body["user"]
    assert User.objects.filter(telegram_id=123456789).count() == 1

    cookie = response.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
    assert cookie["httponly"] is True
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/api/v1/auth/"


@pytest.mark.django_db
def test_login_requires_csrf_and_rejects_invalid_signature(client):
    missing_csrf = client.post(
        "/api/v1/auth/telegram/",
        telegram_payload(),
        format="json",
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "CSRF_FAILED"

    invalid = telegram_payload(telegram_id=123123123)
    invalid["hash"] = "0" * 64
    response = client.post(
        "/api/v1/auth/telegram/",
        invalid,
        format="json",
        **csrf_headers(client),
    )
    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_INVALID_TELEGRAM_PAYLOAD"
    assert not User.objects.filter(telegram_id=123123123).exists()


@pytest.mark.django_db
def test_login_rejects_inactive_user_and_generates_fallback_username(client):
    inactive = User.objects.create_user(
        username="inactive_telegram",
        password=None,
        telegram_id=765432101,
        is_active=False,
    )
    inactive_response = client.post(
        "/api/v1/auth/telegram/",
        telegram_payload(telegram_id=inactive.telegram_id),
        format="json",
        **csrf_headers(client),
    )
    assert inactive_response.status_code == 401
    assert inactive_response.json()["code"] == "AUTH_USER_INACTIVE"

    fallback_response = login(
        client,
        telegram_payload(telegram_id=765432102, username=None),
    )
    assert fallback_response.json()["user"]["username"] == "user_765432102"


@pytest.mark.django_db
def test_exact_replay_fails_but_fresh_payload_creates_new_session(client):
    payload = telegram_payload(telegram_id=222222222)
    login(client, payload)
    second_client = APIClient(enforce_csrf_checks=True)

    replay = second_client.post(
        "/api/v1/auth/telegram/",
        payload,
        format="json",
        **csrf_headers(second_client),
    )
    assert replay.status_code == 401
    assert replay.json()["code"] == "AUTH_INVALID_TELEGRAM_PAYLOAD"

    fresh = telegram_payload(
        telegram_id=222222222,
        auth_date=int(time.time()) + 1,
        username="changed_telegram",
    )
    fresh_response = login(second_client, fresh)
    assert fresh_response.status_code == 200
    assert User.objects.filter(telegram_id=222222222).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_logins_over_http_share_one_user():
    auth_date = int(time.time())
    payloads = [
        telegram_payload(
            telegram_id=989898989,
            auth_date=auth_date,
            username="race_one",
        ),
        telegram_payload(
            telegram_id=989898989,
            auth_date=auth_date,
            username="race_two",
        ),
    ]

    def login_in_thread(payload: dict[str, object]):
        thread_client = APIClient(enforce_csrf_checks=True)
        return thread_client.post(
            "/api/v1/auth/telegram/",
            payload,
            format="json",
            **csrf_headers(thread_client),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(login_in_thread, payloads))

    assert [response.status_code for response in responses] == [200, 200]
    user = User.objects.get(telegram_id=989898989)
    assert {response.json()["user"]["id"] for response in responses} == {user.pk}
    assert RefreshSession.objects.filter(user=user).count() == 2


@pytest.mark.django_db
def test_me_patch_validates_username_and_preserves_telegram_identity(client):
    response = login(client, telegram_payload(telegram_id=333333333))
    access_token = response.json()["access_token"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    profile = client.get("/api/v1/auth/me/")
    assert profile.status_code == 200
    assert profile.json()["username"] == "anna_example"
    assert profile.json()["has_telegram"] is True

    updated = client.patch(
        "/api/v1/auth/me/",
        {"username": "  New.Name "},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.json()["username"] == "new.name"
    assert updated.json()["has_telegram"] is True

    invalid = client.patch(
        "/api/v1/auth/me/",
        {"username": "bad space"},
        format="json",
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"
    non_object = client.patch(
        "/api/v1/auth/me/",
        [],
        format="json",
    )
    assert non_object.status_code == 400
    assert non_object.json()["code"] == "INVALID_REQUEST"

    unknown = client.patch(
        "/api/v1/auth/me/",
        {"username": "valid_name", "role": "admin"},
        format="json",
    )
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "INVALID_REQUEST"

    for invalid_username in ("", "ab", "a" * 31, "bad space", "русский"):
        boundary = client.patch(
            "/api/v1/auth/me/",
            {"username": invalid_username},
            format="json",
        )
        assert boundary.status_code == 422
        assert boundary.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.django_db
def test_username_collision_returns_409_and_preserves_previous_value(client):
    first = login(client, telegram_payload(telegram_id=444444444))
    first_access = first.json()["access_token"]
    second_client = APIClient(enforce_csrf_checks=True)
    second = login(
        second_client,
        telegram_payload(telegram_id=555555555, auth_date=int(time.time()) + 1),
    )
    second_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {second.json()['access_token']}"
    )
    assert (
        second_client.patch(
            "/api/v1/auth/me/",
            {"username": "collision_name"},
            format="json",
        ).status_code
        == 200
    )

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {first_access}")
    collision = client.patch(
        "/api/v1/auth/me/",
        {"username": "COLLISION_NAME"},
        format="json",
    )
    assert collision.status_code == 409
    assert collision.json()["code"] == "USERNAME_TAKEN"
    assert User.objects.get(telegram_id=444444444).username == "anna_example"


@pytest.mark.django_db
def test_refresh_does_not_rotate_and_logout_revokes_session(client):
    login(client, telegram_payload(telegram_id=666666666))
    refresh_value = client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    headers = csrf_headers(client)
    missing_refresh_csrf = client.post(
        "/api/v1/auth/token/refresh/",
        format="json",
    )
    assert missing_refresh_csrf.status_code == 403
    assert missing_refresh_csrf.json()["code"] == "CSRF_FAILED"

    missing_logout_csrf = client.post(
        "/api/v1/auth/logout/",
        format="json",
    )
    assert missing_logout_csrf.status_code == 403
    assert missing_logout_csrf.json()["code"] == "CSRF_FAILED"

    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh_value
    refreshed = client.post(
        "/api/v1/auth/token/refresh/",
        format="json",
        **headers,
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["expires_in"] == 900
    assert client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value == refresh_value

    logout = client.post(
        "/api/v1/auth/logout/",
        format="json",
        **csrf_headers(client),
    )
    assert logout.status_code == 204

    client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh_value
    repeated_logout = client.post(
        "/api/v1/auth/logout/",
        format="json",
        **csrf_headers(client),
    )
    assert repeated_logout.status_code == 204

    stale_client = APIClient(enforce_csrf_checks=True)
    stale_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh_value
    failed_refresh = stale_client.post(
        "/api/v1/auth/token/refresh/",
        format="json",
        **csrf_headers(stale_client),
    )
    assert failed_refresh.status_code == 401
    assert failed_refresh.json()["code"] == "AUTH_REFRESH_REVOKED"
    stale_cookie = failed_refresh.cookies[settings.AUTH_REFRESH_COOKIE_NAME]
    assert stale_cookie["max-age"] == 0
    assert stale_cookie["path"] == "/api/v1/auth/"


@pytest.mark.django_db
def test_logout_all_revokes_multiple_sessions(client):
    first = login(client, telegram_payload(telegram_id=777777777))
    first_access = first.json()["access_token"]
    first_refresh = client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    login(
        client,
        telegram_payload(
            telegram_id=777777777,
            auth_date=int(time.time()) + 1,
            username="another_telegram_name",
        ),
    )
    second_refresh = client.cookies[settings.AUTH_REFRESH_COOKIE_NAME].value
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {first_access}")

    logout_all = client.post("/api/v1/auth/logout-all/", format="json")
    assert logout_all.status_code == 204

    for refresh_value in (first_refresh, second_refresh):
        session_client = APIClient(enforce_csrf_checks=True)
        session_client.cookies[settings.AUTH_REFRESH_COOKIE_NAME] = refresh_value
        failed = session_client.post(
            "/api/v1/auth/token/refresh/",
            format="json",
            **csrf_headers(session_client),
        )
        assert failed.status_code == 401
        assert failed.json()["code"] == "AUTH_REFRESH_REVOKED"


@pytest.mark.django_db
def test_delete_requires_confirmation_and_stale_access_cannot_reuse_account(client):
    payload = telegram_payload(telegram_id=888888888)
    login_response = login(client, payload)
    access_token = login_response.json()["access_token"]
    user_id = login_response.json()["user"]["id"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    missing_confirmation = client.delete(
        "/api/v1/auth/me/",
        {"confirmation": "NO"},
        format="json",
    )
    assert missing_confirmation.status_code == 400
    assert User.objects.filter(pk=user_id).exists()

    deleted = client.delete(
        "/api/v1/auth/me/",
        {"confirmation": "DELETE"},
        format="json",
    )
    assert deleted.status_code == 204
    assert deleted.cookies[settings.AUTH_REFRESH_COOKIE_NAME]["max-age"] == 0
    assert not User.objects.filter(pk=user_id).exists()

    stale = client.get("/api/v1/auth/me/")
    assert stale.status_code == 401
    assert stale.json()["code"] == "AUTHENTICATION_REQUIRED"
    repeated_delete = client.delete(
        "/api/v1/auth/me/",
        {"confirmation": "DELETE"},
        format="json",
    )
    assert repeated_delete.status_code == 401
    assert repeated_delete.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert not User.objects.filter(pk=user_id).exists()

    fresh_client = APIClient(enforce_csrf_checks=True)
    fresh = login(
        fresh_client,
        telegram_payload(
            telegram_id=888888888,
            auth_date=int(time.time()) + 1,
        ),
    )
    assert fresh.status_code == 200
    assert fresh.json()["user"]["id"] != user_id


@pytest.mark.django_db
def test_telegram_login_throttles_by_ip(client):
    statuses = []
    for telegram_id in range(900000001, 900000012):
        response = client.post(
            "/api/v1/auth/telegram/",
            telegram_payload(telegram_id=telegram_id),
            format="json",
            **csrf_headers(client),
        )
        statuses.append(response.status_code)

    assert statuses[-1] == 429
    assert (
        client.post(
            "/api/v1/auth/telegram/",
            telegram_payload(telegram_id=999999999),
            format="json",
            **csrf_headers(client),
        ).json()["code"]
        == "THROTTLED"
    )


@pytest.mark.django_db
def test_refresh_and_account_mutations_are_throttled(client):
    login_response = login(
        client,
        telegram_payload(telegram_id=900000100),
    )
    access_token = login_response.json()["access_token"]
    refresh_statuses = []
    for _ in range(31):
        refresh_statuses.append(
            client.post(
                "/api/v1/auth/token/refresh/",
                format="json",
                **csrf_headers(client),
            ).status_code
        )
    assert refresh_statuses[29] == 200
    assert refresh_statuses[30] == 429

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    mutation_statuses = []
    for index in range(11):
        mutation_statuses.append(
            client.patch(
                "/api/v1/auth/me/",
                {"username": f"throttle_{index}"},
                format="json",
            ).status_code
        )
    assert mutation_statuses[:10] == [200] * 10
    assert mutation_statuses[10] == 429


@pytest.mark.django_db
def test_openapi_contains_auth_routes(client):
    response = client.get(
        "/api/v1/schema/",
        HTTP_ACCEPT="application/json",
    )

    assert response.status_code == 200
    assert b"/api/v1/auth/telegram/" in response.content
    assert b"/api/v1/auth/token/refresh/" in response.content
    schema = json.loads(response.content)
    refresh_parameters = schema["paths"]["/api/v1/auth/token/refresh/"]["post"][
        "parameters"
    ]
    assert {parameter["name"] for parameter in refresh_parameters} >= {
        "X-CSRFToken",
        "medcore_refresh",
    }
    assert schema["components"]["securitySchemes"]["bearerAuth"] == {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    assert schema["paths"]["/api/v1/auth/me/"]["get"]["security"] == [
        {"bearerAuth": []}
    ]
