# Quickstart: Telegram auth and user account

## Prerequisites

- Python 3.12 and `uv`.
- PostgreSQL reachable through the configured `DATABASE_*` environment values.
- Redis reachable through `REDIS_URL` for throttling/cache.
- `TELEGRAM_BOT_TOKEN` and a dedicated `JWT_SIGNING_KEY` supplied through the
  environment for real integration. Tests use deterministic fixtures and do
  not use production secrets.

## Setup

```bash
uv sync
uv run python manage.py migrate
```

Set the configured frontend origin in `CORS_ALLOWED_ORIGINS` and
`CSRF_TRUSTED_ORIGINS`. Production must use HTTPS and a single first-party
origin.

## Focused validation

Run the auth app tests first:

```bash
uv run pytest apps/users/tests apps/common/tests
```

The tests prove:

1. valid legacy widget HMAC creates one User and a refresh session;
2. stale, malformed, invalid-signature and exact replay payloads fail;
3. repeated fresh payloads find the same User without changing application
   username;
4. username normalization, allowed characters, length, collision and race
   behavior;
5. Bearer access authentication, expiry, inactive User and auth-version
   checks;
6. refresh success, non-rotation, revocation, logout race and logout-all;
7. CSRF success/failure and scoped throttling;
8. self-delete confirmation, session revocation, hard deletion and stale-token
   no-op behavior;
9. OpenAPI contains every auth route and security requirement.

## Smoke API sequence

1. `GET /api/v1/auth/csrf/` and keep the `csrftoken` cookie plus response token.
2. `POST /api/v1/auth/telegram/` with the token in `X-CSRFToken` and a signed
   widget payload. Confirm `access_token` JSON and HttpOnly `medcore_refresh`
   cookie.
3. Call `GET /api/v1/auth/me/` with the Bearer access token.
4. Call `POST /api/v1/auth/token/refresh/` with the cookie and CSRF header;
   confirm only the access token changes.
5. Call `POST /api/v1/auth/logout/`; confirm refresh fails and the cookie is
   cleared.
6. Authenticate a second session, call `POST /api/v1/auth/logout-all/`, and
   confirm both refresh sessions fail.
7. Call `DELETE /api/v1/auth/me/` with `{"confirmation":"DELETE"}`; confirm
   the User and sessions are gone and a stale token receives 401.

## Project checks

After focused tests pass, run exactly:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```
