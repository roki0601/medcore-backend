import os

from .base import *  # noqa: F403

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-only")
ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "[::1]",
    "89.125.116.118",
    "prepmed.ru",
]

AUTH_REFRESH_COOKIE_SECURE = False
OPENAPI_PUBLIC = True
DEV_AUTH_ENABLED = True
