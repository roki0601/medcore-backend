# Production readiness

This document is the deployment checklist for the MVP backend. Production runs
with `config.settings.production` behind an HTTPS reverse proxy. The frontend
and backend use one first-party origin; cross-origin cookie deployment is not
supported by the MVP contract.

## Required production environment

The production settings module refuses to start when any of these values is
missing or unsafe:

- `DJANGO_SECRET_KEY` — random, at least 50 characters;
- `JWT_SIGNING_KEY` — a different random key, at least 50 characters;
- `TELEGRAM_BOT_TOKEN`;
- `DJANGO_ALLOWED_HOSTS` — explicit hostnames, never `*`;
- `DATABASE_NAME`, `DATABASE_USER`, `DATABASE_PASSWORD`, `DATABASE_HOST`,
  `DATABASE_PORT`;
- `REDIS_URL`;
- `ROBOKASSA_MERCHANT_LOGIN`, `ROBOKASSA_PASSWORD_1`,
  `ROBOKASSA_PASSWORD_2`, `ROBOKASSA_HASH_ALGORITHM`, and explicit
  `ROBOKASSA_TEST_MODE=true|false`. Test mode also requires
  `ROBOKASSA_TEST_PASSWORD_1` and `ROBOKASSA_TEST_PASSWORD_2`.
- `MEDIA_STORAGE_BACKEND=local` and `MEDIA_STORAGE_ROOT=/app/media-storage` on the current VPS. S3 credentials are required only when `MEDIA_STORAGE_BACKEND=s3`.

Do not put real secrets in `.env.example`, images, or repository history.

## Optional environment

- `DATABASE_CONN_MAX_AGE` (default `60`) and
  `DATABASE_CONN_HEALTH_CHECKS` (default `true`);
- `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` when a separately hosted
  first-party origin is explicitly approved;
- `MEDIA_S3_ENDPOINT_URL` for S3-compatible providers other than AWS;
- `MEDIA_S3_REGION`, `MEDIA_S3_ADDRESSING_STYLE`, media size and URL TTLs;
- `LOG_LEVEL` (default `INFO`);
- `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`,
  `SECURE_HSTS_INCLUDE_SUBDOMAINS`, and `SECURE_HSTS_PRELOAD`;
- `SECURE_PROXY_SSL_HEADER_ENABLED` to trust the reverse proxy's
  `X-Forwarded-Proto: https` header.

The HTTPS controls are deliberately opt-in. Enable HSTS only after every
subdomain covered by the policy is HTTPS-only. Enable the proxy header only
when the reverse proxy strips and sets the header; never accept that header
directly from an untrusted public client.

## Auth, cookies, CORS and CSRF

The refresh cookie is `HttpOnly`, `Secure` in production, `SameSite=Lax`,
scoped to `/api/v1/auth/`, and expires after 30 days. Cookie-authenticated
login, refresh, and logout requests require the CSRF header. Keep the frontend
and backend on one site/origin, or use an approved same-origin proxy.

Credentialed CORS must list explicit HTTPS origins. Do not use a wildcard. The
Robokassa ResultURL is a DRF APIView and remains CSRF-exempt by normal DRF
behavior; do not add a global CSRF exemption.

## Database and Redis

Run migrations as a separate deployment step before routing traffic:

```bash
python manage.py migrate --noinput --settings=config.settings.production
```

`CONN_MAX_AGE` is configurable and connection health checks are enabled by
default. Redis is cache infrastructure and also backs security throttles; a
Redis outage must make readiness fail instead of silently disabling throttles.
Readiness does not call Telegram, Robokassa, or object storage.

## Media storage

The current VPS uses `MEDIA_STORAGE_BACKEND=local` with
`MEDIA_STORAGE_ROOT=/app/media-storage`, mounted from the named volume
`prepmed_media_data`. Files must not live only in the container filesystem.
`deploy.sh` does not delete or recreate that volume. S3 support remains in the
application; select it by setting `MEDIA_STORAGE_BACKEND=s3` and the
`MEDIA_S3_*` credentials. Local storage is single-node: `manage.py check`
emits `media.W001` and still exits successfully.

Back up the media volume separately from PostgreSQL. A database dump does not
contain these files. `scripts/prod/backup-media.sh` writes a timestamped
archive of `/app/media-storage`. Copy that archive off the VPS; a copy on this
machine is not disaster recovery.

Access and upload capability URLs are short-lived credentials. Configure the
reverse proxy and application logs so paths containing
`/api/v1/media/file/<token>/` and `/api/v1/media/upload/<token>/` are excluded
or redacted.

## Robokassa

Set `ROBOKASSA_TEST_MODE` explicitly. Use `false` for production merchant
accounts. When it is `true`, checkout and ResultURL use
`ROBOKASSA_TEST_PASSWORD_1` and `ROBOKASSA_TEST_PASSWORD_2`, not the live
passwords. ResultURL authenticity and amount checks are performed server-side;
SuccessURL/FailURL are buyer UX endpoints and do not grant entitlement.

## Startup and checks

With safe production values, run:

```bash
python manage.py check --deploy --settings=config.settings.production
python manage.py check --settings=config.settings.production
python manage.py makemigrations --check --dry-run --settings=config.settings.production
```

Do not ignore security or schema warnings. Collect static files and run the
explicit migration step before starting Gunicorn. The Compose web healthcheck
uses readiness and should not route traffic until PostgreSQL and Redis are
reachable.

## Health endpoints

- `GET /api/v1/health/` — backwards-compatible liveness endpoint;
- `GET /api/v1/health/live/` — liveness only; no DB/Redis dependency;
- `GET /api/v1/health/ready/` — checks PostgreSQL with `SELECT 1` and Redis
  cache; returns `200` when both are available and `503` otherwise.

No health endpoint makes external provider calls.

## Pre-deploy checklist

- [ ] Production settings module selected.
- [ ] All required environment variables are present and secret values are
      supplied through the deployment secret manager.
- [ ] Allowed hosts and CORS/CSRF origins are explicit.
- [ ] HTTPS proxy behavior, redirect, HSTS, and forwarded-proto trust are
      explicitly configured and tested.
- [ ] S3 bucket is private and credentials have least privilege.
- [ ] Capability URL access logs are disabled/redacted.
- [ ] `check --deploy`, migration check, and schema generation are clean.
- [ ] Migrations completed before traffic is enabled.
- [ ] Readiness returns `200` from the deployed web service.

## Post-deploy smoke test

1. Check `/api/v1/health/live/` and `/api/v1/health/ready/`.
2. Verify catalog and anonymous demo content.
3. Verify Telegram login, CSRF-protected refresh, logout, and account deletion
   with test credentials.
4. Verify free-content access and denial for paid content without entitlement.
5. Verify payment initialization is configured for the intended Robokassa mode;
   do not call the real provider as part of CI.
6. Verify profile, learning state, dashboard, and protected media access.
7. Confirm logs contain no JWTs, refresh cookies, Telegram/Robokassa/S3
   secrets, request payloads, or capability URLs.

## PrepMed VPS

Production root is `/root/dev/medcore`. `PREPMED_ROOT` overrides it. Caddy stays
a host systemd service; this repository does not change the Caddyfile. The
live site already proxies `/api/*`, `/admin/*` and `/static/*` to
`127.0.0.1:8000` and everything else to `127.0.0.1:3000`.

```text
/root/dev/medcore/
  medcore-backend/
  medcore-frontend/
  .env.backend          # mode 600, not in git
  .env.frontend         # mode 600, not in git
  deploy.sh             # symlink to medcore-backend/scripts/prod/deploy.sh
  backups/              # same-VPS dumps; not disaster recovery
  .prepmed-postgres-ready
```

Do not publish 3000, 8000, 5432 or 6379. The public listeners stay 22, 80 and
443.

### Current runtime, audited 2026-09-22

These are the processes the first deploy replaces. Do not delete their data.

| Runtime | Identity | Port | Data |
| --- | --- | --- | --- |
| Postgres | compose project `medcore-backend`, container `medcore-backend-postgres-1`, file `medcore-backend/compose.yaml` | `127.0.0.1:5432` | volume `medcore-backend_postgres_data` at `/var/lib/postgresql/data`. Database `medcore`, 29 applied migrations, about 10 MB. |
| Redis | container `medcore-backend-redis-1` | `127.0.0.1:6379` | volume `medcore-backend_redis_data` at `/data`. AOF off, `DBSIZE` 0, `dump.rdb` is an empty snapshot. |
| Frontend | `docker run` container `medcore-frontend`, not a compose service | `127.0.0.1:3000` | bind `/root/dev/medcore/medcore-frontend:/app`. No database volume. |
| Backend | host gunicorn, cwd `/root/dev/medcore/medcore-backend`, not a systemd unit | `127.0.0.1:8000` | no database of its own. |

The new project name is `prepmed`. Its volumes are `prepmed_postgres_data` and
`prepmed_redis_data`. They are not the legacy volumes. Starting the new
postgres without a copy would create an empty database while the real data
stays in `medcore-backend_postgres_data`. `deploy.sh` refuses that.

### First cutover

`./deploy.sh` does this itself. It does not delete legacy volumes or stop the
legacy postgres/redis containers.

1. Build the production images. A failed build leaves the current site running.
2. If `prepmed_postgres_data` has no `PG_VERSION` and
   `medcore-backend_postgres_data` exists, `pg_dump -Fc` the running legacy
   postgres into `/root/dev/medcore/backups/cutover-*.dump`, start the new
   postgres on the new volume, `pg_restore`, and compare the
   `django_migrations` fingerprint. The legacy container keeps serving
   `127.0.0.1:5432` during the copy.
3. Copy `dump.rdb` into `prepmed_redis_data` when it exists. Redis currently
   has no keys; the legacy volume is still kept.
4. Run `migrate` and `check` against the new database. The old gunicorn and
   frontend are still up, so a failed migration does not take the site down.
5. Stop only container `medcore-frontend` (`docker stop`, not `docker rm`) and
   the host gunicorn whose cwd is the backend checkout. If 3000 or 8000 is
   held by anything else, the script stops. It does not start the new
   frontend or backend on an occupied port.
6. Start the new backend and frontend on `127.0.0.1:8000` and
   `127.0.0.1:3000`, then check localhost and `https://prepmed.ru`.

A successful cutover writes `/root/dev/medcore/.prepmed-postgres-ready`. Later
deploys see that marker and do not dump again. If the new volume already has
Postgres data and the marker is missing, deploy aborts instead of guessing.

Keep `DATABASE_NAME=medcore`. The legacy database name is `medcore`.

After the new stack is healthy and an offsite copy of the cutover dump exists,
the old containers can be stopped by hand. Do not run `docker volume rm` on
`medcore-backend_postgres_data` or `medcore-backend_redis_data` until that
copy exists. `deploy.sh` never removes those volumes.

Rollback before trusting the new stack: `docker stop` the new backend and
frontend, `docker start medcore-frontend`, and start the old host gunicorn
again. The legacy postgres container is still on `127.0.0.1:5432`.

### Setup on this VPS

The clones are already at `/root/dev/medcore`. Do not move them.

```bash
cd /root/dev/medcore
ln -sfn medcore-backend/scripts/prod/deploy.sh deploy.sh
install -m 600 /dev/null .env.backend
install -m 600 /dev/null .env.frontend
```

Fill the env files, then run `./deploy.sh` by hand. Add GitHub Actions secrets
only after that succeeds. The workflow is inert until it is on `main`. Its
SSH command is `cd /root/dev/medcore && ./deploy.sh`.

GitHub secrets, SSH only: `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`, optional
`PROD_PORT` and `PROD_KNOWN_HOSTS`. Do not store application secrets in GitHub.

### Backup

`scripts/prod/backup-db.sh` writes a timestamped `pg_dump -Fc` under
`/root/dev/medcore/backups` and exits non-zero on failure. A copy on this VPS
is not disaster recovery. Copy it off the server.

### Reboot

New compose services use `restart: unless-stopped`. The legacy postgres,
redis and frontend containers have restart policy `no`, and the host gunicorn
is not a systemd unit. After the cutover, a reboot should bring back only
Docker, the new containers and Caddy.

- [ ] `systemctl is-enabled docker caddy` is `enabled`.
- [ ] After reboot, the `prepmed` project shows backend, frontend, postgres and redis up.
- [ ] Legacy volume `medcore-backend_postgres_data` still exists.
- [ ] `curl --fail --header 'Host: prepmed.ru' http://127.0.0.1:8000/api/v1/health/ready/`
- [ ] `curl --fail http://127.0.0.1:3000/`
- [ ] `curl --fail https://prepmed.ru/`
- [ ] `curl --fail https://prepmed.ru/api/v1/health/ready/`
- [ ] 3000 and 8000 are bound to `127.0.0.1` only. 5432 and 6379 are not required on the host.

### Rollback

Do not run `docker compose down -v` or `docker system prune -a`.

If the new migration has not run, the legacy database is unchanged. Stop the
new backend/frontend and start the old frontend container and host gunicorn.
If the new migration has run, do not expect a code checkout to undo it.
Restore from the cutover dump or an offsite dump only when the schema must
move backward, and take a fresh dump first. Run `pg_restore` through
`docker compose exec -T postgres`.
