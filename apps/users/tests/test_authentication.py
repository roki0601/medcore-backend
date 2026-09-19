from __future__ import annotations

from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .helpers import TEST_BOT_TOKEN, csrf_headers, telegram_payload

User = get_user_model()


@pytest.fixture(autouse=True)
def configure_telegram(settings):
    settings.TELEGRAM_BOT_TOKEN = TEST_BOT_TOKEN


@pytest.mark.django_db
def test_access_token_rejects_auth_version_mismatch():
    client = APIClient(enforce_csrf_checks=True)
    payload = telegram_payload(telegram_id=121212121)
    csrf = csrf_headers(client)
    login = client.post(
        "/api/v1/auth/telegram/",
        payload,
        format="json",
        **csrf,
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    user = User.objects.get(telegram_id=121212121)
    user.auth_version += 1
    user.save(update_fields=("auth_version", "updated_at"))

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_inactive_user_cannot_use_existing_access_token():
    client = APIClient(enforce_csrf_checks=True)
    login = client.post(
        "/api/v1/auth/telegram/",
        telegram_payload(telegram_id=131313131),
        format="json",
        **csrf_headers(client),
    )
    token = login.json()["access_token"]
    user = User.objects.get(telegram_id=131313131)
    user.is_active = False
    user.save(update_fields=("is_active", "updated_at"))

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    response = client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_USER_INACTIVE"


@pytest.mark.django_db
def test_access_token_rejects_expiry_issuer_audience_type_and_missing_credentials():
    client = APIClient(enforce_csrf_checks=True)
    login = client.post(
        "/api/v1/auth/telegram/",
        telegram_payload(telegram_id=141414141),
        format="json",
        **csrf_headers(client),
    )
    assert login.status_code == 200
    access = AccessToken(login.json()["access_token"])

    access.set_exp(lifetime=timedelta(seconds=-1))
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    expired = client.get("/api/v1/auth/me/")
    assert expired.status_code == 401
    assert expired.json()["code"] == "AUTHENTICATION_REQUIRED"

    def tampered_token(claim: str, value: str) -> str:
        claims = jwt.decode(
            login.json()["access_token"],
            options={"verify_signature": False},
        )
        claims[claim] = value
        return jwt.encode(
            claims,
            settings.JWT_SIGNING_KEY,
            algorithm="HS256",
        )

    wrong_issuer = tampered_token("iss", "wrong-issuer")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {wrong_issuer}")
    wrong_issuer_response = client.get("/api/v1/auth/me/")
    assert wrong_issuer_response.status_code == 401
    assert wrong_issuer_response.json()["code"] == "AUTHENTICATION_REQUIRED"

    wrong_audience = tampered_token("aud", "wrong-audience")
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {wrong_audience}")
    wrong_audience_response = client.get("/api/v1/auth/me/")
    assert wrong_audience_response.status_code == 401
    assert wrong_audience_response.json()["code"] == "AUTHENTICATION_REQUIRED"

    refresh = client.cookies["medcore_refresh"].value
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh}")
    wrong_type = client.get("/api/v1/auth/me/")
    assert wrong_type.status_code == 401
    assert wrong_type.json()["code"] == "AUTHENTICATION_REQUIRED"

    missing = APIClient(enforce_csrf_checks=True).get("/api/v1/auth/me/")
    assert missing.status_code == 401
    assert missing.json()["code"] == "AUTHENTICATION_REQUIRED"


@pytest.mark.django_db
def test_refresh_token_expiry_is_enforced():
    user = User.objects.create_user(username="expiry_user", password=None)
    refresh = RefreshToken.for_user(user)
    refresh["auth_version"] = user.auth_version
    refresh.set_exp(lifetime=timedelta(seconds=-1))
    client = APIClient(enforce_csrf_checks=True)
    client.cookies["medcore_refresh"] = str(refresh)
    csrf = csrf_headers(client)

    response = client.post(
        "/api/v1/auth/token/refresh/",
        format="json",
        **csrf,
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REFRESH_REVOKED"
