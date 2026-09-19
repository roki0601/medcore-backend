#!/usr/bin/env bash
set -euo pipefail

staged_names="$(git diff --cached --name-only --diff-filter=ACMR)"

while IFS= read -r path; do
  [[ -z "$path" ]] && continue
  case "$path" in
    .env.example|*/.env.example|*.example.env)
      ;;
    .env|.env.*|*/.env|*/.env.*|*secret*|*credential*|*private-key*)
      echo "staged sensitive-looking file path: $path" >&2
      exit 1
      ;;
  esac
done <<< "$staged_names"

secret_pattern="-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|gh[opurs]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|sk-[A-Za-z0-9_-]{20,}|AIza[0-9A-Za-z_-]{20,}|[0-9]{8,12}:[A-Za-z0-9_-]{30,}|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"

# Inspect only added text. Searching the whole unified diff makes normal source
# code such as `access_token = response[...]` look like a credential and also
# scans removed lines that will not be committed.
while IFS= read -r path; do
  [[ -z "$path" ]] && continue

  added_lines="$(git diff --cached --unified=0 --no-ext-diff -- "$path" \
    | sed -e '/^+++/d' -e '/^+/s/^+//p')"
  if rg -q -i -- "$secret_pattern" <<< "$added_lines"; then
    echo "staged diff contains a high-confidence secret-like value: $path" >&2
    exit 1
  fi
done <<< "$staged_names"

exit 0
