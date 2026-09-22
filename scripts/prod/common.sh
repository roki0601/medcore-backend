#!/usr/bin/env bash

prepmed_root() {
  printf '%s\n' "${PREPMED_ROOT:-/root/dev/medcore}"
}

prepmed_compose() {
  local root
  root="$(prepmed_root)"
  docker compose \
    --project-name prepmed \
    --env-file "$root/.env.backend" \
    --env-file "$root/.env.frontend" \
    -f "$root/medcore-backend/compose.prod.yaml" \
    "$@"
}
