#!/usr/bin/env bash
# Production deploy for the live VPS layout. Do not rename these directories:
# the running host uses /root/dev/medcore/medcore-backend and medcore-frontend.
# Env files stay beside the clones and are never checked out from git.
set -euo pipefail

ROOT="${PREPMED_ROOT:-/root/dev/medcore}"
BACKEND_DIR="$ROOT/medcore-backend"
FRONTEND_DIR="$ROOT/medcore-frontend"
LOCK_FILE="${PREPMED_DEPLOY_LOCK:-/var/lock/prepmed-deploy.lock}"
META_DIR="$ROOT/.deploy"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY_FRONTEND_CONTAINER="${PREPMED_LEGACY_FRONTEND_CONTAINER:-medcore-frontend}"
HEALTH_ATTEMPTS="${PREPMED_HEALTH_ATTEMPTS:-10}"
HEALTH_INTERVAL="${PREPMED_HEALTH_INTERVAL:-3}"

log() {
  printf '[deploy] %s\n' "$*"
}

die() {
  printf '[deploy] %s\n' "$*" >&2
  exit 1
}

is_sha() {
  [[ "$1" =~ ^[0-9a-f]{40}$ ]]
}

usage() {
  cat <<'EOF'
Usage:
  PREPMED_BACKEND_SHA=<sha> ./deploy.sh
  PREPMED_FRONTEND_SHA=<sha> ./deploy.sh
  PREPMED_BACKEND_SHA=<sha> PREPMED_FRONTEND_SHA=<sha> ./deploy.sh
  ./deploy.sh rollback-backend <sha>
  ./deploy.sh rollback-frontend <sha>

Deploys the exact commit that passed CI. A missing SHA leaves that service
untouched. Rollback rebuilds the application only; it does not reverse
database migrations.
EOF
}

require_sha() {
  local name="$1"
  local value="$2"
  if ! is_sha "$value"; then
    die "$name must be a 40-character git SHA"
  fi
}

checkout_sha() {
  local dir="$1"
  local sha="$2"
  local label="$3"

  if [[ ! -d "$dir/.git" ]]; then
    die "missing git clone: $dir"
  fi
  if [[ -n "$(git -C "$dir" status --porcelain)" ]]; then
    die "$dir has local changes; refusing to deploy"
  fi

  log "$label current: $(git -C "$dir" rev-parse HEAD)"
  log "$label target: $sha"
  git -C "$dir" fetch --prune origin main
  if ! git -C "$dir" cat-file -e "${sha}^{commit}" 2>/dev/null; then
    git -C "$dir" fetch origin "$sha"
  fi
  git -C "$dir" cat-file -e "${sha}^{commit}"
  git -C "$dir" checkout --detach "$sha"
  if [[ "$(git -C "$dir" rev-parse HEAD)" != "$sha" ]]; then
    die "$label checkout landed on $(git -C "$dir" rev-parse HEAD), expected $sha"
  fi
}

parse_args() {
  if [[ $# -eq 0 ]]; then
    return 0
  fi
  case "$1" in
    -h | --help)
      usage
      exit 0
      ;;
    rollback-backend)
      [[ $# -eq 2 ]] || die "usage: ./deploy.sh rollback-backend <sha>"
      require_sha "rollback backend SHA" "$2"
      export PREPMED_BACKEND_SHA="$2"
      export PREPMED_SKIP_MIGRATE=1
      unset PREPMED_FRONTEND_SHA
      ;;
    rollback-frontend)
      [[ $# -eq 2 ]] || die "usage: ./deploy.sh rollback-frontend <sha>"
      require_sha "rollback frontend SHA" "$2"
      export PREPMED_FRONTEND_SHA="$2"
      unset PREPMED_BACKEND_SHA
      ;;
    *)
      die "unknown argument: $1"
      ;;
  esac
}

require_mode_600() {
  local env_file="$1"
  local mode
  if [[ ! -f "$env_file" ]]; then
    die "missing $env_file"
  fi
  mode="$(stat -c %a "$env_file")"
  if [[ "$mode" != "600" ]]; then
    die "$env_file must be mode 600, found $mode"
  fi
}

listener_pids() {
  local port="$1"
  ss -ltnpH "sport = :$port" | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
}

container_on_port() {
  local port="$1"
  docker ps --format '{{.Names}} {{.Ports}}' |
    awk -v port="127.0.0.1:${port}->" 'index($0, port) {print $1}'
}

release_legacy_listeners() {
  local names pid cmd cwd master=""
  names="$(container_on_port 3000 || true)"
  if [[ -n "$names" && "$names" != "$LEGACY_FRONTEND_CONTAINER" && "$names" != "prepmed-frontend-1" ]]; then
    die "port 3000 is held by unexpected container: $names"
  fi
  names="$(container_on_port 8000 || true)"
  if [[ -n "$names" && "$names" != "prepmed-backend-1" ]]; then
    die "port 8000 is held by unexpected container: $names"
  fi

  if docker ps --format '{{.Names}}' | grep -qx "$LEGACY_FRONTEND_CONTAINER"; then
    local source
    source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}' "$LEGACY_FRONTEND_CONTAINER")"
    if [[ "$source" != "$FRONTEND_DIR" ]]; then
      die "$LEGACY_FRONTEND_CONTAINER mount is $source, expected $FRONTEND_DIR"
    fi
    log "stopping legacy frontend container $LEGACY_FRONTEND_CONTAINER"
    docker stop "$LEGACY_FRONTEND_CONTAINER" >/dev/null
  fi

  if [[ -z "$(container_on_port 8000 || true)" ]]; then
    for pid in $(listener_pids 8000); do
      cmd="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
      cwd="$(readlink "/proc/$pid/cwd")"
      if [[ "$cmd" != *gunicorn* || "$cmd" != *config.wsgi* || "$cwd" != "$BACKEND_DIR" ]]; then
        die "port 8000 is held by unexpected process $pid ($cmd)"
      fi
      local ppid
      ppid="$(awk '/^PPid:/ {print $2}' "/proc/$pid/status")"
      if [[ "$ppid" == "1" ]]; then
        master="$pid"
      fi
    done
    if [[ -n "$(listener_pids 8000)" && -z "$master" ]]; then
      die "host gunicorn is listening but its master was not identified"
    fi
    if [[ -n "$master" ]]; then
      log "stopping host gunicorn pid $master"
      kill -TERM "$master"
      local attempt
      for attempt in $(seq 1 30); do
        if ! kill -0 "$master" 2>/dev/null; then
          break
        fi
        sleep 1
      done
      if kill -0 "$master" 2>/dev/null; then
        kill -KILL "$master"
      fi
    fi
  fi

  if [[ -n "$(listener_pids 3000)" && -z "$(container_on_port 3000 || true)" ]]; then
    die "port 3000 is still occupied after stopping $LEGACY_FRONTEND_CONTAINER"
  fi
  if [[ -n "$(listener_pids 8000)" && -z "$(container_on_port 8000 || true)" ]]; then
    die "port 8000 is still occupied after stopping host gunicorn"
  fi
}

wait_healthy() {
  local service="$1"
  local attempt id status
  for attempt in $(seq 1 30); do
    id="$(prepmed_compose ps -q "$service")"
    if [[ -n "$id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id")"
      if [[ "$status" == "healthy" ]]; then
        return 0
      fi
    fi
    sleep 2
  done
  prepmed_compose logs --tail 80 "$service" || true
  die "$service did not become healthy"
}

wait_curl() {
  local label="$1"
  shift
  local attempt=1
  while [[ "$attempt" -le "$HEALTH_ATTEMPTS" ]]; do
    if curl --fail --silent --show-error --max-time 10 "$@"; then
      printf '\n'
      log "$label passed"
      return 0
    fi
    sleep "$HEALTH_INTERVAL"
    attempt=$((attempt + 1))
  done
  die "$label failed after $HEALTH_ATTEMPTS attempts"
}

record_sha() {
  local name="$1"
  local sha="$2"
  install -d -m 700 "$META_DIR"
  printf '%s\n' "$sha" >"$META_DIR/${name}.sha"
  chmod 600 "$META_DIR/${name}.sha"
}

on_error() {
  local line="$1"
  local status="$2"
  trap - ERR
  log "failed at line $line with status $status"
  log "previous backend SHA: ${PREPMED_PREVIOUS_BACKEND_SHA:-unknown}"
  log "previous frontend SHA: ${PREPMED_PREVIOUS_FRONTEND_SHA:-unknown}"
  log "database migrations are not rolled back automatically"
  exit "$status"
}

deploy_backend() {
  local media_volume media_existed=0
  media_volume="${PREPMED_MEDIA_VOLUME:-prepmed_media_data}"
  if docker volume inspect "$media_volume" >/dev/null 2>&1; then
    media_existed=1
  fi

  log "building backend"
  prepmed_compose build backend
  log "ensuring postgres and redis"
  prepmed_compose up -d postgres redis
  wait_healthy postgres
  wait_healthy redis
  "$SCRIPT_DIR/cutover-legacy-data.sh"

  if [[ "${PREPMED_SKIP_MIGRATE:-}" == 1 ]]; then
    log "skipping migrations; application rollback does not roll the database back"
  else
    log "migrations"
    prepmed_compose run --rm --no-deps backend python manage.py showmigrations --plan
    if ! prepmed_compose run --rm --no-deps backend python manage.py migrate --noinput; then
      die "migrate failed; database was not rolled back and the backend container was not replaced"
    fi
  fi
  prepmed_compose run --rm --no-deps backend python manage.py check
  log "collectstatic already ran while building the backend image"

  release_legacy_listeners
  log "starting backend"
  if ! prepmed_compose up -d --no-deps backend; then
    die "backend container did not start; if migrate succeeded, the schema may be ahead of the running app"
  fi
  wait_healthy backend
  wait_curl "backend healthcheck" --header "Host: prepmed.ru" http://127.0.0.1:8000/api/v1/health/ready/
  wait_curl "public backend healthcheck" https://prepmed.ru/api/v1/health/ready/
  if [[ "$media_existed" == 1 ]] && ! docker volume inspect "$media_volume" >/dev/null 2>&1; then
    die "media volume $media_volume disappeared during deploy"
  fi
  record_sha backend "$(git -C "$BACKEND_DIR" rev-parse HEAD)"
  log "backend healthcheck passed"
}

deploy_frontend() {
  log "building frontend"
  prepmed_compose build frontend
  release_legacy_listeners
  log "starting frontend"
  if ! prepmed_compose up -d --no-deps frontend; then
    die "frontend container did not start"
  fi
  wait_healthy frontend
  wait_curl "frontend healthcheck" http://127.0.0.1:3000/
  wait_curl "public frontend healthcheck" https://prepmed.ru/
  record_sha frontend "$(git -C "$FRONTEND_DIR" rev-parse HEAD)"
  log "frontend healthcheck passed"
}

parse_args "$@"

DEPLOY_BACKEND=0
DEPLOY_FRONTEND=0
if [[ -n "${PREPMED_BACKEND_SHA:-}" ]]; then
  require_sha "PREPMED_BACKEND_SHA" "$PREPMED_BACKEND_SHA"
  DEPLOY_BACKEND=1
fi
if [[ -n "${PREPMED_FRONTEND_SHA:-}" ]]; then
  require_sha "PREPMED_FRONTEND_SHA" "$PREPMED_FRONTEND_SHA"
  DEPLOY_FRONTEND=1
fi
if [[ "$DEPLOY_BACKEND" == 0 && "$DEPLOY_FRONTEND" == 0 ]]; then
  usage >&2
  die "set PREPMED_BACKEND_SHA and/or PREPMED_FRONTEND_SHA"
fi

if [[ "${PREPMED_DEPLOY_REEXEC:-}" != 1 ]]; then
  if [[ ! -d "$BACKEND_DIR/.git" || ! -d "$FRONTEND_DIR/.git" ]]; then
    die "missing git clones under $ROOT"
  fi
  install -d -m 755 "$(dirname "$LOCK_FILE")"
  exec 9>"$LOCK_FILE"
  if ! flock -w 1800 9; then
    die "timed out waiting for another production deploy"
  fi
  PREPMED_PREVIOUS_BACKEND_SHA="$(git -C "$BACKEND_DIR" rev-parse HEAD)"
  PREPMED_PREVIOUS_FRONTEND_SHA="$(git -C "$FRONTEND_DIR" rev-parse HEAD)"
  export PREPMED_PREVIOUS_BACKEND_SHA PREPMED_PREVIOUS_FRONTEND_SHA
  if [[ "$DEPLOY_BACKEND" == 1 ]]; then
    checkout_sha "$BACKEND_DIR" "$PREPMED_BACKEND_SHA" backend
  else
    log "backend untouched"
  fi
  if [[ "$DEPLOY_FRONTEND" == 1 ]]; then
    checkout_sha "$FRONTEND_DIR" "$PREPMED_FRONTEND_SHA" frontend
  else
    log "frontend untouched"
  fi
  export PREPMED_DEPLOY_REEXEC=1
  exec "$BACKEND_DIR/scripts/prod/deploy.sh"
fi

# shellcheck disable=SC1091
source "$SCRIPT_DIR/common.sh"
trap 'on_error "$LINENO" "$?"' ERR

require_mode_600 "$ROOT/.env.backend"
require_mode_600 "$ROOT/.env.frontend"
PREPMED_BACKEND_REVISION="$(git -C "$BACKEND_DIR" rev-parse HEAD)"
PREPMED_FRONTEND_REVISION="$(git -C "$FRONTEND_DIR" rev-parse HEAD)"
export PREPMED_BACKEND_REVISION PREPMED_FRONTEND_REVISION
log "backend previous: ${PREPMED_PREVIOUS_BACKEND_SHA:-unknown}"
log "frontend previous: ${PREPMED_PREVIOUS_FRONTEND_SHA:-unknown}"

if [[ "$DEPLOY_BACKEND" == 1 ]]; then
  deploy_backend
else
  log "backend untouched"
fi
if [[ "$DEPLOY_FRONTEND" == 1 ]]; then
  deploy_frontend
else
  log "frontend untouched"
fi

prepmed_compose ps
log "done"
