from __future__ import annotations

import pytest
from django.core.cache import caches
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def use_local_cache(settings):
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "medcore-auth-tests",
        }
    }
    settings.JWT_SIGNING_KEY = "test-jwt-signing-key-with-at-least-32-bytes"
    from rest_framework_simplejwt.settings import api_settings

    api_settings.SIGNING_KEY = settings.JWT_SIGNING_KEY
    caches["default"].clear()


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def make_user(db):
    from django.contrib.auth import get_user_model

    User = get_user_model()

    def _make_user(
        *,
        username: str = "testuser",
        role: str = User.Role.USER,
        is_staff: bool = False,
        is_superuser: bool = False,
        is_active: bool = True,
    ):
        user = User(
            username=username,
            role=role,
            is_staff=is_staff,
            is_superuser=is_superuser,
            is_active=is_active,
        )
        user.set_unusable_password()
        user.save()
        return user

    return _make_user


@pytest.fixture
def authenticate():
    from rest_framework_simplejwt.tokens import RefreshToken

    def _authenticate(client: APIClient, user) -> APIClient:
        access = RefreshToken.for_user(user).access_token
        access["auth_version"] = user.auth_version
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        return client

    return _authenticate
