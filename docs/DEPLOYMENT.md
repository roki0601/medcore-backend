# Production deploy

PrepMed deploys one VPS. Caddy stays a host service. Docker Compose project
`prepmed` runs backend, frontend, Postgres and Redis. This is not Kubernetes,
and images are built on the VPS. Do not run a second deploy mechanism beside
`/root/dev/medcore/deploy.sh`.

The live directories are `medcore-backend` and `medcore-frontend`. Do not rename
them to `backend` and `frontend`.

## Flow

```text
PR → CI → merge to main → CI on main → deploy workflow → SSH → deploy.sh
```

Deploy runs only after a successful CI workflow for a push to `main`. Pull
requests and failed CI do not deploy. Backend and frontend workflows are
independent. A server-side `flock` lets only one deploy run at a time; the
other waits up to 30 minutes.

Each workflow passes the CI commit SHA:

```bash
PREPMED_BACKEND_SHA=<sha> ./deploy.sh
PREPMED_FRONTEND_SHA=<sha> ./deploy.sh
```

`deploy.sh` checks out that exact commit. It does not deploy whatever `main`
happens to be. A backend-only run does not rebuild frontend, and the reverse.
If both SHAs are set, backend is migrated and health-checked before frontend
starts. A backend failure leaves frontend untouched.

## VPS layout

```text
/root/dev/medcore/
  medcore-backend/          # git clone
  medcore-frontend/         # git clone
  deploy.sh                 # symlink to medcore-backend/scripts/prod/deploy.sh
  .env.backend              # mode 600, not in git
  .env.frontend             # mode 600, not in git
  .deploy/backend.sha       # written after a successful backend deploy
  .deploy/frontend.sha      # written after a successful frontend deploy
  .prepmed-postgres-ready
  backups/
```

Caddy is `systemctl` on the host. Application deploys do not restart it. They
only check that `https://prepmed.ru/` and `/api/v1/health/ready/` still answer.

## GitHub secrets

Set these in both repositories. Do not put application secrets in GitHub.

| Secret | Required | Purpose |
| --- | --- | --- |
| `PROD_HOST` | yes | VPS host |
| `PROD_USER` | yes | SSH user. Currently `root`; a dedicated deploy user is safer |
| `PROD_SSH_KEY` | yes | Private key. No password login |
| `PROD_PORT` | no | SSH port, default `22` |
| `PROD_KNOWN_HOSTS` | yes | `ssh-keyscan` output. `StrictHostKeyChecking=yes` |

Create `PROD_KNOWN_HOSTS` from a trusted machine:

```bash
ssh-keyscan -p 22 -H <PROD_HOST>
```

Paste the output into the secret. Do not use `accept-new` in the workflow.

## One-time server setup

These already exist on the current VPS. Repeat them only on a new machine:

```bash
cd /root/dev/medcore
ln -sfn medcore-backend/scripts/prod/deploy.sh deploy.sh
install -m 600 /dev/null .env.backend
install -m 600 /dev/null .env.frontend
install -d -m 700 .deploy
```

Fill the env files on the server. A deploy must not overwrite them. Both clones
must have a clean `git status` before the first automatic deploy. The script
stops if a tracked or untracked change is present; it does not run
`git reset --hard`.

The script currently on the server re-executes itself after checkout. The first
backend deploy after this change installs the new script that way. Do not start
a production deploy from this repository task unless you intend to.

## Manual deploy

```bash
cd /root/dev/medcore
PREPMED_BACKEND_SHA=<40-char-sha> ./deploy.sh
PREPMED_FRONTEND_SHA=<40-char-sha> ./deploy.sh
```

Both at once, backend first:

```bash
PREPMED_BACKEND_SHA=<backend-sha> PREPMED_FRONTEND_SHA=<frontend-sha> ./deploy.sh
```

## Rollback

Application only. Database migrations are never rolled back automatically.

```bash
cd /root/dev/medcore
./deploy.sh rollback-backend <previous-sha>
./deploy.sh rollback-frontend <previous-sha>
```

Previous SHAs are printed in the deploy log and, after a successful deploy, in
`.deploy/backend.sha` and `.deploy/frontend.sha`. If a migration succeeded and
the new container then failed, the log says the schema may be ahead of the
running app. Restore the database from `/root/dev/medcore/backups` only when a
human decides the schema must move backward. Take a fresh dump first.

## Logs and checks

```bash
cd /root/dev/medcore
docker compose --project-name prepmed \
  --env-file .env.backend --env-file .env.frontend \
  -f medcore-backend/compose.prod.yaml logs --tail 100 backend
docker compose --project-name prepmed \
  --env-file .env.backend --env-file .env.frontend \
  -f medcore-backend/compose.prod.yaml logs --tail 100 frontend
cat .deploy/backend.sha .deploy/frontend.sha
curl --fail --header 'Host: prepmed.ru' http://127.0.0.1:8000/api/v1/health/ready/
curl --fail http://127.0.0.1:3000/
curl --fail https://prepmed.ru/
```

GitHub Actions is red when build, migrate, container start, or healthcheck
fails. Healthchecks retry 10 times, 3 seconds apart.

## Failed migration

`deploy.sh` prints `showmigrations --plan`, then runs
`python manage.py migrate --noinput`. It does not run `makemigrations`. If
migrate fails, the backend container is not replaced and the database is not
rolled back. Fix the migration in a new commit, or restore from a backup by
hand. Do not delete volumes and do not run `docker compose down` or
`docker system prune -a` as a recovery step.

## Remaining risk

Deploys still SSH as root. A dedicated deploy user with access only to
`/root/dev/medcore` and the Docker socket would be safer. GitHub concurrency
groups are per repository, so the cross-repo lock is the server `flock`, not
the Actions setting.
