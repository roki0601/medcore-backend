#!/usr/bin/env bash
# Copy the existing VPS database into the new production volume.
# Never deletes the legacy volume or stops the legacy postgres/redis containers.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ROOT="$(prepmed_root)"
MARKER="$ROOT/.prepmed-postgres-ready"
LEGACY_POSTGRES_VOLUME="${PREPMED_LEGACY_POSTGRES_VOLUME:-medcore-backend_postgres_data}"
LEGACY_POSTGRES_CONTAINER="${PREPMED_LEGACY_POSTGRES_CONTAINER:-medcore-backend-postgres-1}"
LEGACY_REDIS_VOLUME="${PREPMED_LEGACY_REDIS_VOLUME:-medcore-backend_redis_data}"
LEGACY_REDIS_CONTAINER="${PREPMED_LEGACY_REDIS_CONTAINER:-medcore-backend-redis-1}"
NEW_POSTGRES_VOLUME="${PREPMED_POSTGRES_VOLUME:-prepmed_postgres_data}"
NEW_REDIS_VOLUME="${PREPMED_REDIS_VOLUME:-prepmed_redis_data}"

volume_exists() {
  docker volume inspect "$1" >/dev/null 2>&1
}

volume_has_file() {
  local volume="$1"
  local path="$2"
  volume_exists "$volume" || return 1
  docker run --rm -v "$volume:/vol:ro" postgres:16-alpine \
    sh -c "test -e /vol/$path"
}

migration_fingerprint() {
  local mode="$1"
  local sql="SELECT count(*) || ' ' || md5(coalesce(string_agg(app || ':' || name, ',' ORDER BY id), '')) FROM django_migrations"
  if [[ "$mode" == "legacy" ]]; then
    docker exec "$LEGACY_POSTGRES_CONTAINER" \
      sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"$sql\""
  else
    prepmed_compose exec -T postgres \
      sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"$sql\""
  fi
}

abort_ambiguous() {
  echo "prepmed postgres volume already has data but $MARKER is missing." >&2
  echo "Refusing to create or overwrite a database. Legacy volume $LEGACY_POSTGRES_VOLUME was not touched." >&2
  exit 1
}

copy_redis_snapshot() {
  if ! volume_exists "$LEGACY_REDIS_VOLUME"; then
    echo "no legacy redis volume; new redis starts empty"
    return 0
  fi
  if volume_has_file "$NEW_REDIS_VOLUME" dump.rdb || volume_has_file "$NEW_REDIS_VOLUME" appendonly.aof; then
    echo "new redis volume already has data; not copying"
    return 0
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx "$LEGACY_REDIS_CONTAINER"; then
    echo "legacy redis container $LEGACY_REDIS_CONTAINER is not running; leaving its volume in place" >&2
    return 0
  fi
  docker volume create "$NEW_REDIS_VOLUME" >/dev/null
  docker exec "$LEGACY_REDIS_CONTAINER" redis-cli BGSAVE >/dev/null
  local attempt
  for attempt in $(seq 1 20); do
    if docker exec "$LEGACY_REDIS_CONTAINER" redis-cli INFO persistence \
      | grep -q '^rdb_bgsave_in_progress:0'; then
      break
    fi
    sleep 1
  done
  if volume_has_file "$LEGACY_REDIS_VOLUME" dump.rdb; then
    docker run --rm \
      -v "$LEGACY_REDIS_VOLUME:/from:ro" \
      -v "$NEW_REDIS_VOLUME:/to" \
      postgres:16-alpine cp /from/dump.rdb /to/dump.rdb
    echo "copied redis dump.rdb from $LEGACY_REDIS_VOLUME; legacy volume kept"
  else
    echo "legacy redis volume has no dump.rdb; new redis starts empty. Legacy volume kept."
  fi
}

restore_postgres() {
  local stamp dump legacy_fp new_fp
  if ! docker ps --format '{{.Names}}' | grep -qx "$LEGACY_POSTGRES_CONTAINER"; then
    echo "legacy postgres container $LEGACY_POSTGRES_CONTAINER is not running; refusing to create an empty database" >&2
    exit 1
  fi
  mkdir -p "$ROOT/backups"
  chmod 700 "$ROOT/backups"
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  dump="$ROOT/backups/cutover-${stamp}.dump"
  echo "dumping $LEGACY_POSTGRES_CONTAINER to $dump"
  docker exec "$LEGACY_POSTGRES_CONTAINER" \
    sh -c 'pg_dump -Fc --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    > "$dump"
  if [[ ! -s "$dump" ]]; then
    echo "legacy pg_dump was empty; old volume was not modified" >&2
    exit 1
  fi
  chmod 600 "$dump"
  legacy_fp="$(migration_fingerprint legacy | tr -d '[:space:]')"
  legacy_count="${legacy_fp%%[!0-9]*}"
  if [[ -z "$legacy_count" || "$legacy_count" == "0" ]]; then
    echo "legacy django_migrations count is empty or zero ($legacy_fp); refusing cutover" >&2
    exit 1
  fi

  prepmed_compose up -d postgres
  local attempt id status
  for attempt in $(seq 1 30); do
    id="$(prepmed_compose ps -q postgres || true)"
    if [[ -n "$id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$id")"
      if [[ "$status" == "healthy" ]]; then
        break
      fi
    fi
    sleep 2
  done
  if [[ "${status:-}" != "healthy" ]]; then
    echo "new postgres did not become healthy; legacy volume was not modified" >&2
    exit 1
  fi

  if ! prepmed_compose exec -T postgres \
    sh -c 'pg_restore --no-owner --no-acl --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    < "$dump"; then
    echo "pg_restore failed. Legacy volume $LEGACY_POSTGRES_VOLUME was not modified." >&2
    echo "Incomplete new volume $NEW_POSTGRES_VOLUME was left in place for inspection. Do not delete the legacy volume." >&2
    exit 1
  fi
  new_fp="$(migration_fingerprint new | tr -d '[:space:]')"
  if [[ "$new_fp" != "$legacy_fp" ]]; then
    echo "restored migration fingerprint $new_fp != legacy $legacy_fp" >&2
    echo "Legacy volume was not modified. Do not start the new backend over this volume." >&2
    exit 1
  fi
  cat > "$MARKER" <<EOF
source_volume=$LEGACY_POSTGRES_VOLUME
source_container=$LEGACY_POSTGRES_CONTAINER
dump=$dump
django_migrations=$new_fp
EOF
  chmod 600 "$MARKER"
  echo "postgres cutover verified ($new_fp). Legacy volume kept."
}

if [[ -f "$MARKER" ]]; then
  if volume_has_file "$NEW_POSTGRES_VOLUME" PG_VERSION; then
    echo "postgres cutover marker present; not creating a new database"
    exit 0
  fi
  echo "$MARKER exists but $NEW_POSTGRES_VOLUME has no PG_VERSION. Refusing to continue." >&2
  exit 1
fi

if volume_has_file "$NEW_POSTGRES_VOLUME" PG_VERSION; then
  if volume_exists "$LEGACY_POSTGRES_VOLUME"; then
    abort_ambiguous
  fi
  echo "new postgres volume exists and no legacy volume is present"
  exit 0
fi

if volume_exists "$LEGACY_POSTGRES_VOLUME"; then
  echo "legacy volume $LEGACY_POSTGRES_VOLUME found; copying into $NEW_POSTGRES_VOLUME"
  copy_redis_snapshot
  restore_postgres
  exit 0
fi

echo "no legacy postgres volume; a fresh database will be created by migrate"
exit 0
