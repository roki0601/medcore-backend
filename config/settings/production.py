import os

from django.core.exceptions import ImproperlyConfigured

from . import base
from .base import *  # noqa: F403,F405

DEBUG = False


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production")
    return value


def _strong_secret(name: str) -> str:
    value = _required_env(name)
    if len(value) < 50 or len(set(value)) < 5:
        raise ImproperlyConfigured(
            f"{name} must be at least 50 characters and contain varied characters"
        )
    return value


def _required_bool(name: str) -> bool:
    value = _required_env(name).lower()
    if value not in {"true", "false"}:
        raise ImproperlyConfigured(f"{name} must be exactly true or false")
    return value == "true"


SECRET_KEY = _strong_secret("DJANGO_SECRET_KEY")

ALLOWED_HOSTS = base.env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production")
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS must list explicit hosts in production"
    )

JWT_SIGNING_KEY = _strong_secret("JWT_SIGNING_KEY")
TELEGRAM_BOT_TOKEN = _required_env("TELEGRAM_BOT_TOKEN")

for _database_setting in (
    "DATABASE_NAME",
    "DATABASE_USER",
    "DATABASE_PASSWORD",
    "DATABASE_HOST",
    "DATABASE_PORT",
):
    DATABASES["default"][_database_setting.removeprefix("DATABASE_")] = _required_env(  # noqa: F405
        _database_setting
    )

REDIS_URL = _required_env("REDIS_URL")
CACHES["default"]["LOCATION"] = REDIS_URL  # noqa: F405
ROBOKASSA_MERCHANT_LOGIN = _required_env("ROBOKASSA_MERCHANT_LOGIN")
ROBOKASSA_PASSWORD_1 = _required_env("ROBOKASSA_PASSWORD_1")
ROBOKASSA_PASSWORD_2 = _required_env("ROBOKASSA_PASSWORD_2")
ROBOKASSA_HASH_ALGORITHM = _required_env("ROBOKASSA_HASH_ALGORITHM").lower()
if ROBOKASSA_HASH_ALGORITHM not in {"md5", "sha256"}:
    raise ImproperlyConfigured("ROBOKASSA_HASH_ALGORITHM must be either md5 or sha256")
ROBOKASSA_TEST_MODE = _required_bool("ROBOKASSA_TEST_MODE")

AUTH_REFRESH_COOKIE_SECURE = True
OPENAPI_PUBLIC = False

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = base.env_bool("SECURE_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = base.env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = base.env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if base.env_bool("SECURE_PROXY_SSL_HEADER_ENABLED", False)
    else None
)
