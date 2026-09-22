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

`compose.yaml` remains the existing local/server-like stack used by
`make compose-up`, `make compose-migrate` and `make compose-down`. It is not
the production VPS topology.

Production on the VPS uses `compose.prod.yaml` from `/opt/prepmed`. Caddy stays
on the host. PostgreSQL and Redis publish no host ports. See
`docs/operations/production-readiness.md`.

```bash
make compose-migrate
make compose-up
make compose-logs
```

Stop the local stack with `make compose-down`. Do not use that Makefile target
for the production project.
