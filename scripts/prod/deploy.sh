#!/usr/bin/env bash
set -euo pipefail

ROOT="${PREPMED_ROOT:-/root/dev/medcore}"
BACKEND_DIR="$ROOT/medcore-backend"
FRONTEND_DIR="$ROOT/medcore-frontend"
LOCK_FILE="$ROOT/.deploy.lock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY_FRONTEND_CONTAINER="${PREPMED_LEGACY_FRONTEND_CONTAINER:-medcore-frontend}"

if [[ ! -d "$BACKEND_DIR/.git" || ! -d "$FRONTEND_DIR/.git" ]]; then
  echo "missing git clones under $ROOT" >&2
  exit 1
fi

if [[ "${PREPMED_DEPLOY_REEXEC:-}" != 1 ]]; then
  exec 9>"$LOCK_FILE"
  if ! flock -w 1800 9; then
    echo "timed out waiting for another production deploy" >&2
    exit 1
  fi

  pull_main() {
    local dir="$1"
    local expected="${2:-}"
    git -C "$dir" fetch origin main
    if [[ -n "$(git -C "$dir" status --porcelain)" ]]; then
      echo "$dir has local changes; refusing to deploy" >&2
      exit 1
    fi
    git -C "$dir" checkout main
    git -C "$dir" merge --ff-only origin/main
    if [[ -n "$expected" ]]; then
      local actual
      actual="$(git -C "$dir" rev-parse HEAD)"
      if [[ "$actual" != "$expected" ]]; then
        echo "$dir is $actual, CI verified $expected; a newer main deploy must run" >&2
        exit 0
      fi
    fi
  }

  pull_main "$BACKEND_DIR" "${PREPMED_BACKEND_SHA:-}"
  pull_main "$FRONTEND_DIR" "${PREPMED_FRONTEND_SHA:-}"
  export PREPMED_DEPLOY_REEXEC=1
  exec "$BACKEND_DIR/scripts/prod/deploy.sh"
fi

# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

require_mode_600() {
  local env_file="$1"
  local mode
  if [[ ! -f "$env_file" ]]; then
    echo "missing $env_file" >&2
    exit 1
  fi
  mode="$(stat -c %a "$env_file")"
  if [[ "$mode" != "600" ]]; then
    echo "$env_file must be mode 600, found $mode" >&2
    exit 1
  fi
}

listener_pids() {
  local port="$1"
  ss -ltnpH "sport = :$port" | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
}

container_on_port() {
  local port="$1"
  docker ps --format '{{.Names}} {{.Ports}}' \
    | awk -v port="127.0.0.1:${port}->" 'index($0, port) {print $1}'
}

release_legacy_listeners() {
  local names pid cmd cwd master=""
  names="$(container_on_port 3000 || true)"
  if [[ -n "$names" && "$names" != "$LEGACY_FRONTEND_CONTAINER" && "$names" != "prepmed-frontend-1" ]]; then
    echo "port 3000 is held by unexpected container: $names" >&2
    exit 1
  fi
  names="$(container_on_port 8000 || true)"
  if [[ -n "$names" && "$names" != "prepmed-backend-1" ]]; then
    echo "port 8000 is held by unexpected container: $names" >&2
    exit 1
  fi

  if docker ps --format '{{.Names}}' | grep -qx "$LEGACY_FRONTEND_CONTAINER"; then
    local source
    source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app"}}{{.Source}}{{end}}{{end}}' "$LEGACY_FRONTEND_CONTAINER")"
    if [[ "$source" != "$FRONTEND_DIR" ]]; then
      echo "$LEGACY_FRONTEND_CONTAINER mount is $source, expected $FRONTEND_DIR" >&2
      exit 1
    fi
    echo "stopping legacy frontend container $LEGACY_FRONTEND_CONTAINER"
    docker stop "$LEGACY_FRONTEND_CONTAINER" >/dev/null
  fi

  if [[ -z "$(container_on_port 8000 || true)" ]]; then
    for pid in $(listener_pids 8000); do
      cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline")"
      cwd="$(readlink "/proc/$pid/cwd")"
      if [[ "$cmd" != *gunicorn* || "$cmd" != *config.wsgi* || "$cwd" != "$BACKEND_DIR" ]]; then
        echo "port 8000 is held by unexpected process $pid ($cmd)" >&2
        exit 1
      fi
      local ppid
      ppid="$(awk '/^PPid:/ {print $2}' "/proc/$pid/status")"
      if [[ "$ppid" == "1" ]]; then
        master="$pid"
      fi
    done
    if [[ -n "$(listener_pids 8000)" && -z "$master" ]]; then
      echo "host gunicorn is listening but its master was not identified; refusing to kill it" >&2
      exit 1
    fi
    if [[ -n "$master" ]]; then
      echo "stopping host gunicorn pid $master"
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
    echo "port 3000 is still occupied after stopping $LEGACY_FRONTEND_CONTAINER" >&2
    exit 1
  fi
  if [[ -n "$(listener_pids 8000)" && -z "$(container_on_port 8000 || true)" ]]; then
    echo "port 8000 is still occupied after stopping host gunicorn" >&2
    exit 1
  fi
}

require_mode_600 "$ROOT/.env.backend"
require_mode_600 "$ROOT/.env.frontend"

export PREPMED_REVISION="$(
  git -C "$BACKEND_DIR" rev-parse --short=12 HEAD
)-$(git -C "$FRONTEND_DIR" rev-parse --short=12 HEAD)"

prepmed_compose build
"$SCRIPT_DIR/cutover-legacy-data.sh"

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
  echo "$service did not become healthy" >&2
  prepmed_compose ps
  return 1
}

prepmed_compose up -d postgres redis
wait_healthy postgres
wait_healthy redis

prepmed_compose run --rm --no-deps backend python manage.py migrate --noinput
prepmed_compose run --rm --no-deps backend python manage.py check

if [[ ! -f "$ROOT/.prepmed-postgres-ready" ]]; then
  cat > "$ROOT/.prepmed-postgres-ready" <<EOF
source_volume=fresh
django_migrations=created-by-migrate
EOF
  chmod 600 "$ROOT/.prepmed-postgres-ready"
fi

release_legacy_listeners

prepmed_compose up -d backend frontend
wait_healthy backend
wait_healthy frontend

wait_curl() {
  local label="$1"
  shift
  local attempt
  for attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 10 "$@"; then
      echo
      echo "ok $label"
      return 0
    fi
    sleep 2
  done
  echo "failed $label" >&2
  return 1
}

wait_curl "backend ready" --header "Host: prepmed.ru" http://127.0.0.1:8000/api/v1/health/ready/
wait_curl "frontend" http://127.0.0.1:3000/
wait_curl "public site" https://prepmed.ru/
wait_curl "public ready" https://prepmed.ru/api/v1/health/ready/

prepmed_compose ps
