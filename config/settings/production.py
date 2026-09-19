import os

from django.core.exceptions import ImproperlyConfigured

from . import base
from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production")

ALLOWED_HOSTS = base.env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must be set in production")

if not os.environ.get("JWT_SIGNING_KEY"):
    raise ImproperlyConfigured("JWT_SIGNING_KEY must be set in production")
if not os.environ.get("TELEGRAM_BOT_TOKEN"):
    raise ImproperlyConfigured("TELEGRAM_BOT_TOKEN must be set in production")

AUTH_REFRESH_COOKIE_SECURE = True
OPENAPI_PUBLIC = False

CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

SESSION_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
