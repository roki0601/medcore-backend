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
- `MEDIA_STORAGE_BACKEND=s3`, `MEDIA_S3_BUCKET`, `MEDIA_S3_ACCESS_KEY`, and
  `MEDIA_S3_SECRET_KEY`.

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

Production must use private S3-compatible object storage. The Django system
checks reject local storage, unknown backends, and incomplete bucket/credential
configuration. Access and upload capability URLs are short-lived credentials.
Configure the reverse proxy and application/access logs so paths containing
`/api/v1/media/file/<token>/` and `/api/v1/media/upload/<token>/` are excluded
or redacted; capability tokens must not appear in logs, metrics, or error
reports.

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

Production for `https://prepmed.ru` is a Docker Compose project on the existing
VPS. Caddy remains a host systemd service and is not moved into Docker. Do not
change the firewall from this repository. The public listener set should be
22, 80 and 443 only. Do not publish 3000, 8000, 5432 or 6379. Frontend and
backend bind `127.0.0.1` so only Caddy on the host can reach them.

Server layout:

```text
/opt/prepmed/
  medcore-backend/
  medcore-frontend/
  .env.backend          # mode 600, not in git
  .env.frontend         # mode 600, not in git
  deploy.sh             # symlink to medcore-backend/scripts/prod/deploy.sh
  backups/              # same-VPS dumps; not disaster recovery
```

`compose.prod.yaml` is invoked from `/opt/prepmed` by `scripts/prod/deploy.sh`.
It does not replace `compose.yaml`. Migrations run once per deploy, before the
new backend and frontend containers replace the running ones. A failed
migration stops the deploy and leaves the previous containers in place.

`NEXT_PUBLIC_*` values are frontend build args, not backend secrets. The
production API base URL is `https://prepmed.ru/api/v1`. Server components in
the frontend container use that public URL. The compose file maps `prepmed.ru`
and `www.prepmed.ru` to the host gateway so those server reads reach Caddy
without hairpin NAT. Keep `SECURE_SSL_REDIRECT=false`: Caddy terminates TLS,
and localhost health checks are HTTP. Set `SECURE_PROXY_SSL_HEADER_ENABLED=true`
so Django trusts Caddy's `X-Forwarded-Proto`. Port 8000 is bound to localhost,
which is the trust boundary for that header.

The production image installs the `storage-s3` extra and runs `collectstatic`
at build time. WhiteNoise continues to serve `/static/`; Caddy keeps proxying
`/static/*` to the backend. No separate static server is added.

### Initial setup

Both GitHub repositories are private. The VPS needs a read-only deploy key for
each repository. Application secrets stay in the env files, not in GitHub.

```bash
sudo mkdir -p /opt/prepmed
sudo chown "$USER:$USER" /opt/prepmed
cd /opt/prepmed
git clone git@github.com:roki0601/medcore-backend.git
git clone git@github.com:roki0601/medcore-frontend.git
ln -sfn medcore-backend/scripts/prod/deploy.sh deploy.sh
install -m 600 /dev/null .env.backend
install -m 600 /dev/null .env.frontend
```

Fill the env files from the commented production block in `.env.example` and
the frontend `.env.example`. Then run `./deploy.sh` once by hand. Add the
GitHub Actions secrets only after that manual deploy works. The deploy
workflow is inert until it is on `main`.

GitHub secrets, SSH only:

- `PROD_HOST`
- `PROD_USER`
- `PROD_SSH_KEY`
- `PROD_PORT` optional
- `PROD_KNOWN_HOSTS` optional; without it the runner trusts the host key on
  first use

Do not store `DJANGO_SECRET_KEY`, database passwords, Telegram or Robokassa
secrets in GitHub.

### Backup

`scripts/prod/backup-db.sh` writes a timestamped `pg_dump -Fc` file under
`/opt/prepmed/backups` and exits non-zero on failure. A copy on this VPS is
not disaster recovery. Copy the dump off the server after every backup you
intend to rely on.

### Reboot

Docker services use `restart: unless-stopped`. After a reboot, recovery is
Docker starting, containers starting, and Caddy starting via systemd. No manual
process start should be required.

- [ ] `systemctl is-enabled docker caddy` is `enabled`.
- [ ] After reboot, `docker compose ps` shows backend, frontend, postgres and
      redis up.
- [ ] `curl --fail --header 'Host: prepmed.ru' http://127.0.0.1:8000/api/v1/health/ready/`
- [ ] `curl --fail http://127.0.0.1:3000/`
- [ ] `curl --fail https://prepmed.ru/`
- [ ] `curl --fail https://prepmed.ru/api/v1/health/ready/`
- [ ] `ss -ltn` does not show public listeners on 3000, 8000, 5432 or 6379.

### Rollback

Do not run `docker compose down -v` or `docker system prune -a`. Those can
delete the database volume or the images needed to recover.

If migrate has not run, check out the previous `main` commits and run
`./deploy.sh` again. If migrate has run, do not expect a code checkout to undo
schema changes. Restore an offsite `pg_dump -Fc` only when the schema and data
must move backward:

```bash
pg_restore --clean --if-exists --no-owner --no-acl \
  -U "$POSTGRES_USER" -d "$POSTGRES_DB" /path/to/prepmed.dump
```

Run that restore through `docker compose exec -T postgres`. Take a fresh dump
before a restore.
