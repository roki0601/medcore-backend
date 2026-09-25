from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from .helpers import csrf_headers

User = get_user_model()


@pytest.fixture
def client():
    return APIClient(enforce_csrf_checks=True)


def _login(client, persona="demo"):
    return client.post(
        "/api/v1/auth/dev/",
        {"persona": persona},
        format="json",
        **csrf_headers(client),
    )


@pytest.mark.django_db
def test_dev_login_disabled_without_flag(client, settings):
    settings.DEBUG = True
    settings.DEV_AUTH_ENABLED = False
    response = _login(client)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"
    assert not User.objects.filter(username="demo").exists()


@pytest.mark.django_db
def test_dev_login_disabled_without_debug(client, settings):
    settings.DEBUG = False
    settings.DEV_AUTH_ENABLED = True
    response = _login(client)
    assert response.status_code == 404
    assert response.json()["code"] == "RESOURCE_NOT_FOUND"


@pytest.mark.django_db
def test_dev_login_issues_tokens_for_demo_persona(client, settings):
    settings.DEBUG = True
    settings.DEV_AUTH_ENABLED = True
    response = _login(client, "demo")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "demo"
    assert body["user"]["has_telegram"] is False
    assert body["access_token"]
    assert "medcore_refresh" in response.cookies

    me = client.get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {body['access_token']}",
    )
    assert me.status_code == 200
    assert me.json()["username"] == "demo"


@pytest.mark.django_db
def test_dev_login_issues_tokens_and_subscription_for_premium_persona(client, settings):
    settings.DEBUG = True
    settings.DEV_AUTH_ENABLED = True
    response = _login(client, "premium")
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "premium"
    assert body["user"]["has_telegram"] is False
    assert body["access_token"]
    assert "medcore_refresh" in response.cookies

    from apps.subscriptions.selectors import get_active_subscription

    user = User.objects.get(username="premium")
    assert get_active_subscription(user) is not None


@pytest.mark.django_db
def test_dev_login_requires_csrf(client, settings):
    settings.DEBUG = True
    settings.DEV_AUTH_ENABLED = True
    response = client.post("/api/v1/auth/dev/", {"persona": "demo"}, format="json")
    assert response.status_code == 403
