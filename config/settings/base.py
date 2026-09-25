import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.environ.get(name)
    if value is None:
        return default or []
    return [item.strip() for item in value.split(",") if item.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-local-only-change-me")
DEBUG = env_bool("DJANGO_DEBUG")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_AUTH_MAX_AGE = int(os.environ.get("TELEGRAM_AUTH_MAX_AGE", "86400"))
TELEGRAM_AUTH_FUTURE_SKEW = int(os.environ.get("TELEGRAM_AUTH_FUTURE_SKEW", "60"))
AUTH_REFRESH_COOKIE_NAME = "medcore_refresh"
AUTH_REFRESH_COOKIE_PATH = "/api/v1/auth/"
AUTH_REFRESH_COOKIE_SAMESITE = "Lax"
AUTH_REFRESH_COOKIE_SECURE = env_bool("AUTH_REFRESH_COOKIE_SECURE", not DEBUG)
AUTH_REFRESH_COOKIE_MAX_AGE = 30 * 24 * 60 * 60
OPENAPI_PUBLIC = env_bool("OPENAPI_PUBLIC", DEBUG)
DEV_AUTH_ENABLED = env_bool("DEV_AUTH_ENABLED", DEBUG)

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "VERIFYING_KEY": None,
    "AUDIENCE": "medcore-frontend",
    "ISSUER": "medcore-backend",
    "JWK_URL": None,
    "LEEWAY": 0,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "sub",
    "JTI_CLAIM": "jti",
    "TOKEN_TYPE_CLAIM": "token_type",
}

AUTHENTICATION_CLASSES = ("apps.users.authentication.VersionedJWTAuthentication",)

# One environment-managed integration credential for the external content API.
# An unset/empty value denies every integration request (fail closed).
MEDCORE_CONTENT_API_KEY = os.environ.get("MEDCORE_CONTENT_API_KEY", "")

# Provider-neutral object storage for media. ``local`` is a dev/test backend and
# is refused by a Django system check when DEBUG is False; ``s3`` uses the
# optional ``storage-s3`` dependency group.
MEDIA_STORAGE_BACKEND = os.environ.get("MEDIA_STORAGE_BACKEND", "local")
MEDIA_STORAGE_ROOT = os.environ.get(
    "MEDIA_STORAGE_ROOT", str(BASE_DIR / "media-storage")
)
MEDIA_S3_ENDPOINT_URL = os.environ.get("MEDIA_S3_ENDPOINT_URL", "")
MEDIA_S3_BUCKET = os.environ.get("MEDIA_S3_BUCKET", "")
MEDIA_S3_REGION = os.environ.get("MEDIA_S3_REGION", "us-east-1")
MEDIA_S3_ACCESS_KEY = os.environ.get("MEDIA_S3_ACCESS_KEY", "")
MEDIA_S3_SECRET_KEY = os.environ.get("MEDIA_S3_SECRET_KEY", "")
MEDIA_S3_ADDRESSING_STYLE = os.environ.get("MEDIA_S3_ADDRESSING_STYLE", "path")
MEDIA_ALLOWED_MIME_TYPES = ("image/png", "image/jpeg", "image/webp", "image/gif")
MEDIA_MAX_UPLOAD_BYTES = int(
    os.environ.get("MEDIA_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))
)
# Django's request-body limits must not be tighter than the declared media
# limit: the 2.5 MB defaults would reject a legal 3-5 MiB upload with
# RequestDataTooBig (400, outside the error envelope) before the media view sees
# it. Both limits derive from MEDIA_MAX_UPLOAD_BYTES.
DATA_UPLOAD_MAX_MEMORY_SIZE = MEDIA_MAX_UPLOAD_BYTES
FILE_UPLOAD_MAX_MEMORY_SIZE = MEDIA_MAX_UPLOAD_BYTES
MEDIA_UPLOAD_URL_TTL = int(os.environ.get("MEDIA_UPLOAD_URL_TTL", "600"))
MEDIA_ACCESS_URL_TTL = int(os.environ.get("MEDIA_ACCESS_URL_TTL", "600"))
MEDIA_UPLOAD_TOKEN_SALT = "medcore.media.upload"
MEDIA_ACCESS_TOKEN_SALT = "medcore.media.access"
# The two content-owned media decisions reached from ``apps.media`` through
# ``import_string``, so that the media app never imports the content app.
MEDIA_ACCESS_POLICY_PROVIDER = "apps.content.media_policy.decide_media_access"
MEDIA_DELETE_GUARD_PROVIDER = "apps.content.media_policy.guard_media_deletion"

# Simple flashcard ladder (days) for feature 003: ``know`` advances one step and
# stays on the last one, ``repeat`` resets to the first. Values are project
# defaults, not environment configuration.
LEARNING_FLASHCARD_INTERVALS = (1, 3, 7, 14, 30)

THROTTLE_RATES = {
    "telegram_login": "10/min",
    "telegram_login_user": "5/min",
    "refresh": "30/min",
    "refresh_session": "30/min",
    "account_mutation": "10/min",
    "catalog": "120/min",
    "content_read": "60/min",
    "search": "60/min",
    "integration_write": "120/min",
    "media_upload": "30/min",
    "media_metadata": "60/min",
    "media_access": "60/min",
    "learning_read": "120/min",
    "learning_progress": "60/min",
    "learning_review": "60/min",
    "learning_attempt": "60/min",
    "subscriptions_read": "60/min",
    "subscriptions_payment": "30/min",
    "subscriptions_result": "120/min",
}


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.common.apps.CommonConfig",
    "apps.users.apps.UsersConfig",
    "apps.content.apps.ContentConfig",
    "apps.learning.apps.LearningConfig",
    "apps.subscriptions.apps.SubscriptionsConfig",
    "apps.media.apps.MediaConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.common.middleware.APIRequestDataTooBigMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DATABASE_NAME", "medcore"),
        "USER": os.environ.get("DATABASE_USER", "medcore"),
        "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
        "HOST": os.environ.get("DATABASE_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DATABASE_PORT", "5432"),
        "CONN_MAX_AGE": int(os.environ.get("DATABASE_CONN_MAX_AGE", "60")),
        "CONN_HEALTH_CHECKS": env_bool("DATABASE_CONN_HEALTH_CHECKS", True),
        "TEST": {
            "NAME": os.environ.get("DATABASE_TEST_NAME", "medcore_test"),
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        )
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Asia/Yekaterinburg"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "users.User"

REDIS_URL = os.environ.get(
    "REDIS_URL",
    f"redis://{os.environ.get('REDIS_HOST', '127.0.0.1')}"
    f":{os.environ.get('REDIS_PORT', '6379')}/1",
)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = env_bool("CORS_ALLOW_CREDENTIALS", True)
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": AUTHENTICATION_CLASSES,
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.StandardPagination",
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.ScopedRateThrottle",),
    "DEFAULT_THROTTLE_RATES": THROTTLE_RATES,
    "EXCEPTION_HANDLER": "apps.common.exceptions.exception_handler",
}

CSRF_FAILURE_VIEW = "apps.common.views.csrf_failure"

SPECTACULAR_SETTINGS = {
    "TITLE": "MedCore API",
    "DESCRIPTION": "Versioned MedCore backend API.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "ContentBlockStatusEnum": "apps.content.models.ContentBlock.Status",
        "TopicStatusEnum": "apps.content.models.Topic.Status",
        "SubscriptionStatusEnum": "apps.subscriptions.models.Subscription.Status",
        "PaymentStatusEnum": "apps.subscriptions.models.Payment.Status",
        "TopicProgressStatusEnum": "apps.learning.models.UserTopicProgress.Status",
        "QuizAttemptStatusEnum": "apps.learning.models.QuizAttempt.Status",
    },
}

ROBOKASSA_MERCHANT_LOGIN = os.environ.get("ROBOKASSA_MERCHANT_LOGIN", "")
ROBOKASSA_PASSWORD_1 = os.environ.get("ROBOKASSA_PASSWORD_1", "")
ROBOKASSA_PASSWORD_2 = os.environ.get("ROBOKASSA_PASSWORD_2", "")
ROBOKASSA_TEST_PASSWORD_1 = os.environ.get("ROBOKASSA_TEST_PASSWORD_1", "")
ROBOKASSA_TEST_PASSWORD_2 = os.environ.get("ROBOKASSA_TEST_PASSWORD_2", "")
ROBOKASSA_HASH_ALGORITHM = os.environ.get("ROBOKASSA_HASH_ALGORITHM", "sha256")
ROBOKASSA_TEST_MODE = env_bool("ROBOKASSA_TEST_MODE", True)
ROBOKASSA_BASE_URL = os.environ.get(
    "ROBOKASSA_BASE_URL", "https://auth.robokassa.ru/Merchant/Index.aspx"
)

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip().upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
