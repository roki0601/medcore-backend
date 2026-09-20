#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

run_model_smoke() {
  local label="$1"
  local role="$2"
  local expected="OMP_SMOKE_${label}_OK"
  local output

  output="$(./scripts/ai/omp-project \
    --no-session \
    --no-tools \
    --no-skills \
    --no-rules \
    --model "$role" \
    -p "Return exactly $expected" 2>&1)"

  if ! grep -Fq "$expected" <<< "$output"; then
    echo "$label smoke failed" >&2
    printf '%s\n' "$output" >&2
    exit 1
  fi
  echo "$label: OK"
}

run_model_smoke GROK_PLAN @plan
run_model_smoke GEMINI_REVIEW @senior_review

./scripts/ai/check-git-safety.sh
echo "git safety check: OK"
