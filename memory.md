# Project memory

## Backend foundation

- Python 3.12 and `uv` are the project runtime and dependency-management baseline.
- Django settings are split into `base`, `local` and `production` modules.
- The custom `users.User` model is the configured `AUTH_USER_MODEL`; the first
  migration is already committed.
- Initial app boundaries are `common`, `users`, `content`, `learning`,
  `subscriptions` and `media`.
- The first slice intentionally does not implement JWT, Telegram auth, refresh
  sessions or domain content models.

## Runtime

- Local development uses PostgreSQL and Redis already running on the host.
- The server Compose stack contains Gunicorn web, PostgreSQL 16 and Redis 7.
- Redis is configured as Django cache only.
- Compose migrations are explicit through the one-shot `migrate` service and
  `make compose-migrate`; web startup does not run migrations implicitly.

## Quality gates

- Ruff is the formatter and linter; generated Django migrations are excluded.
- Pre-commit runs Ruff checks and formatting through the project `uv` environment.
- GitHub Actions runs formatting, lint, Django checks, migration checks and tests
  against PostgreSQL 16 and Redis 7 services.

## Source of truth

Product and architecture decisions are maintained in the neighboring
`medcore-docs` repository. Accepted decisions there take precedence over
implementation defaults.
