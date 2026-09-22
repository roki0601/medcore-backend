#!/usr/bin/env bash
set -euo pipefail

ROOT="${PREPMED_ROOT:-/opt/prepmed}"
BACKEND_DIR="$ROOT/medcore-backend"
FRONTEND_DIR="$ROOT/medcore-frontend"
LOCK_FILE="$ROOT/.deploy.lock"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

require_mode_600 "$ROOT/.env.backend"
require_mode_600 "$ROOT/.env.frontend"

export PREPMED_REVISION="$(
  git -C "$BACKEND_DIR" rev-parse --short=12 HEAD
)-$(git -C "$FRONTEND_DIR" rev-parse --short=12 HEAD)"

prepmed_compose build
prepmed_compose up -d postgres redis

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

wait_healthy postgres
wait_healthy redis

prepmed_compose run --rm --no-deps backend python manage.py migrate --noinput
prepmed_compose run --rm --no-deps backend python manage.py check

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
