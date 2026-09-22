#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ROOT="$(prepmed_root)"
DEST_DIR="${PREPMED_BACKUP_DIR:-$ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST_DIR/prepmed-${STAMP}.dump"

mkdir -p "$DEST_DIR"
chmod 700 "$DEST_DIR"

tmp="$(mktemp "$DEST_DIR/.prepmed-${STAMP}.dump.partial.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

prepmed_compose exec -T postgres \
  sh -c 'pg_dump -Fc --no-owner --no-acl -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  > "$tmp"

if [[ ! -s "$tmp" ]]; then
  echo "pg_dump produced an empty file" >&2
  exit 1
fi

mv "$tmp" "$OUT"
trap - EXIT
chmod 600 "$OUT"
echo "$OUT"
