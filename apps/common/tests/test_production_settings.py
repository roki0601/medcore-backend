from __future__ import annotations

import os
import subprocess
import sys

import pytest

LONG_SECRET = "a" * 45 + "BC123"
BASE_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.production",
    "DJANGO_SECRET_KEY": LONG_SECRET,
    "DJANGO_ALLOWED_HOSTS": "api.example.test",
    "JWT_SIGNING_KEY": LONG_SECRET,
    "TELEGRAM_BOT_TOKEN": "123:telegram-token",
    "DATABASE_NAME": "medcore",
    "DATABASE_USER": "medcore",
    "DATABASE_PASSWORD": "database-password",
    "DATABASE_HOST": "postgres",
    "DATABASE_PORT": "5432",
    "REDIS_URL": "redis://redis:6379/1",
    "ROBOKASSA_TEST_MODE": "false",
}


def _import_production(overrides: dict[str, str | None] | None = None):
    env = {key: value for key, value in BASE_ENV.items()}
    for key, value in (overrides or {}).items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    process_env = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": os.getcwd(),
        "PYTHON_DOTENV_DISABLED": "1",
        **env,
    }
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=process_env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "name",
    [
        "DATABASE_NAME",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
        "DATABASE_HOST",
        "DATABASE_PORT",
        "REDIS_URL",
    ],
)
def test_production_requires_database_and_redis_settings(name):
    result = _import_production({name: None})

    assert result.returncode != 0
    assert name in result.stderr


@pytest.mark.parametrize(
    "name",
    ["DJANGO_SECRET_KEY", "JWT_SIGNING_KEY"],
)
def test_production_rejects_weak_signing_keys(name):
    result = _import_production({name: "short"})

    assert result.returncode != 0
    assert name in result.stderr


def test_production_rejects_wildcard_allowed_hosts():
    result = _import_production({"DJANGO_ALLOWED_HOSTS": "*"})

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


@pytest.mark.parametrize("value", [None, "yes", "0", "TRUE-ish"])
def test_production_requires_explicit_robokassa_test_mode(value):
    result = _import_production({"ROBOKASSA_TEST_MODE": value})

    assert result.returncode != 0
    assert "ROBOKASSA_TEST_MODE" in result.stderr


def test_production_accepts_explicit_proxy_security_configuration():
    result = _import_production(
        {
            "SECURE_SSL_REDIRECT": "true",
            "SECURE_HSTS_SECONDS": "31536000",
            "SECURE_PROXY_SSL_HEADER_ENABLED": "true",
        }
    )

    assert result.returncode == 0, result.stderr
