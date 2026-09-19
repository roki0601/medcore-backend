from __future__ import annotations

import pytest
from django.core.cache import caches


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
