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

secret_pattern="-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|\\b(api[_-]?key|access[_-]?token|client[_-]?secret|password|secret)\\s*[:=]\\s*[\\\"']?[A-Za-z0-9_./+=-]{12,}"
staged_diff="$(git diff --cached --binary --no-ext-diff | sed 's/UFANET_LOCAL_API_KEY/[PROJECT_API_KEY_PLACEHOLDER]/g')"
if rg -q -i -- "$secret_pattern" <<< "$staged_diff"; then
  echo "staged diff contains a secret-like value" >&2
  exit 1
fi

exit 0
