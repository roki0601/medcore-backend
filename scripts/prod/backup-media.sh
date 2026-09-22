#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

ROOT="$(prepmed_root)"
VOLUME="${PREPMED_MEDIA_VOLUME:-prepmed_media_data}"
DEST_DIR="${PREPMED_BACKUP_DIR:-$ROOT/backups}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$DEST_DIR/prepmed-media-${STAMP}.tar.gz"

mkdir -p "$DEST_DIR"
chmod 700 "$DEST_DIR"

tmp="$(mktemp "$DEST_DIR/.prepmed-media-${STAMP}.tar.gz.partial.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

docker run --rm -v "$VOLUME:/app/media-storage:ro" postgres:16-alpine \
  tar -C /app/media-storage -czf - . > "$tmp"

if [[ ! -s "$tmp" ]]; then
  echo "media archive is empty" >&2
  exit 1
fi

mv "$tmp" "$OUT"
trap - EXIT
chmod 600 "$OUT"
echo "$OUT"
