#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

QWEN_BASE_URL="http://127.0.0.1:8055"

curl -fsS "$QWEN_BASE_URL/health" >/dev/null
models_json="$(curl -fsS "$QWEN_BASE_URL/v1/models")"
if ! grep -Fq 'Qwen3-Coder-Next-NVFP4' <<< "$models_json"; then
  echo "Qwen model is missing from $QWEN_BASE_URL/v1/models" >&2
  exit 1
fi

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

run_model_smoke QWEN @default
run_model_smoke LUNA @plan
run_model_smoke DEEPSEEK @senior_review

./scripts/ai/check-git-safety.sh
echo "git safety check: OK"
