# Project-local OMP setup

This directory contains the MedCore backend OMP configuration. It does not
modify global OMP credentials/settings or neighboring repositories.

The normal backend flow is intentionally small:

```text
Grok DESIGN / SPEC
  -> Gemini DESIGN_REVIEW
  -> Grok IMPLEMENT
  -> Ruff + Django + migration check + pytest
  -> Gemini FINAL_REVIEW (BLOCKER/HIGH only)
  -> Grok fixes material findings
  -> final deterministic gate
  -> PR
```

There is no standing advisor loop and no ordinary Grok self-review chain.

## Model roles

- Grok 4.6 — manager, design/planning, implementation and ordinary backend work;
- Grok Build 0.1 — mechanical commit-sized work;
- Gemini 3.8 Flash — bounded design/spec review and bounded final review;
- Claude Opus 4.6 — emergency escalation only.

Run from repository root:

```bash
./scripts/ai/omp-project --model @plan --approval-mode yolo
```

Do not add `--advisor` to ordinary sessions.

## Feature selection

Approved/shipped implementation specs remain under `specs/`.

Future work first goes through `backend-features/README.md`. Those briefs are
deliberately detailed so the manager does not spend model budget rediscovering
known boundaries.

Rules:

- `READY_FOR_SPEC` → prepare the missing spec/decision packet only;
- `READY_FOR_IMPLEMENTATION` → compact file/module plan, then code;
- `BLOCKED` → do not start design/implementation;
- a documented owner-level `TBD` is not resolved by agent preference.

## Normal review budget

The normal implementation-ready feature gets two Gemini calls:

1. `spec-reviewer` after Grok design/plan;
2. `senior-reviewer` only after the deterministic backend gate is green.

Each reports at most five BLOCKER/HIGH findings. Ignore MEDIUM/LOW/nits,
optional refactors and checks already covered by tooling.

Do not automatically re-run Gemini after fixes. A second final review is only
for a fix that materially changes auth/security, a public API, migration/data
lifecycle, or transaction/concurrency architecture.

## Validation

Match GitHub CI:

```bash
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest --create-db
```

Workers use narrow targeted checks. The manager runs the full gate before final
Gemini review.

Note: `make ci` currently invokes the formatting target rather than
`ruff format --check`; use the explicit commands above when producing final CI
evidence.

## Repository preflight

For a new backend feature, inspect/fast-forward only `medcore-docs` and
`medcore-backend` according to `AGENTS.md`. Frontend is outside backend OMP
write scope.

Never hide dirty/diverged repositories with stash/reset/rebase.

## Delivery

The manager may stage intended files, run `scripts/ai/check-git-safety.sh`,
commit, push a feature branch and create/update a PR after validation.

Never merge or auto-merge. Never commit secrets, tokens, cookies or payment
credentials.

Material decisions go to `.omp/decisions/`; completed/blocked run reports go
to `.omp/reports/`. Keep reports concise and in Russian.
