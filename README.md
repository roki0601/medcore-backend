# MedCore backend

Django backend for MedCore. The project uses Python 3.12, `uv`, PostgreSQL and
Redis as a cache.

## Local development

Local development expects PostgreSQL and Redis to be already running on the
host. Copy `.env.example` to `.env`, set local credentials, then run:

```bash
make install
make migrate
make up
```

The API is available at `http://127.0.0.1:8000`, health check at
`/api/v1/health/`, and OpenAPI UI at `/api/v1/docs/`.

Useful checks:

```bash
make check
make lint
make format
make test
make pre-commit-install
make pre-commit
```

## Server containers

The Compose stack is intended for server-like runs and includes web, PostgreSQL
16 and Redis 7. Provide production values in `.env`, then run migrations
explicitly before starting the web service:

```bash
make compose-migrate
make compose-up
make compose-logs
```

Stop the stack with `make compose-down`. The web container runs Gunicorn; a
reverse proxy is intentionally outside this repository.
