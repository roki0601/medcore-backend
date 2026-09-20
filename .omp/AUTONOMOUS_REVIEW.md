# Backend autonomous review and decision policy

This policy keeps unattended OMP execution bounded and cheap. Grok owns
feature design/planning and implementation. Gemini is used only as an
independent read-only reviewer at two normal gates. Deterministic backend checks
run before the final Gemini review.

## Source precedence

Use this order:

1. accepted decisions in sibling `medcore-docs`;
2. approved feature specs under `specs/`;
3. backend architecture documents and `AGENTS.md`;
4. `backend-features/` briefs for not-yet-specified work;
5. current code and tests.

A `TBD` is not permission to choose. A blocked feature remains blocked until
an authoritative decision resolves it.

## Default workflow

For implementation-ready work use:

`DESIGN -> DESIGN_REVIEW -> IMPLEMENT -> QUALITY_GATE -> FINAL_REVIEW -> READY_FOR_PR`

For a feature marked `READY_FOR_SPEC`, DESIGN means writing the spec/decision
packet only. Do not cross into implementation while required owner decisions
remain unresolved.

### 1. DESIGN — Grok

Read only the selected feature's authoritative inputs.

If an approved spec already exists, produce one compact implementation plan:
affected modules, migrations, invariants, API changes, test budget and exact
writable zones.

If the feature is `READY_FOR_SPEC`, build the spec around already accepted
facts and surface only the unresolved decisions explicitly listed in the
feature brief. Do not launch architecture/scout/reviewer swarms to rediscover
those same blockers.

Do not ask Grok to independently review its own design.

### 2. DESIGN_REVIEW — Gemini once

Spawn `spec-reviewer` exactly once.

Give it a compact packet:

- selected feature brief/spec;
- accepted material decisions;
- Grok's design/plan;
- only the relevant code paths.

Gemini reports only `BLOCKER` and `HIGH` findings, maximum five.

Ignore style preferences, optional abstractions, speculative future-proofing,
MEDIUM/LOW/nits and checks covered by the deterministic gate.

If an owner-level `TBD` remains, the verdict is `BLOCKED`; do not spend more
review rounds debating it.

### 3. IMPLEMENT — Grok

Implementation starts only from an accepted implementation-ready contract.

Prefer one implementer for one coherent feature. Use at most two workers only
when writable zones, migrations and dependency chains are genuinely disjoint.

Workers:

1. finish a coherent code+test change;
2. run the narrowest relevant checks once;
3. fix concrete failures;
4. rerun only failed targeted checks while converging.

Do not spawn a Grok self-reviewer after implementation. Tests, Ruff, Django
checks and migration checks are the ordinary feedback loop.

### 4. QUALITY_GATE — deterministic checks before Gemini

Before final model review run the GitHub-CI-equivalent gate:

```text
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest --create-db
```

Do not call final Gemini review while any command is red.

If one command fails, Grok fixes the concrete failure and reruns only that
failed command. After convergence, run the full gate once again for clean final
evidence.

### 5. FINAL_REVIEW — Gemini once

After the full gate is green, spawn `senior-reviewer` exactly once with:

- approved design/spec;
- final diff/changed paths;
- migration/API contract changes;
- concise gate results.

Review only material risks:

- contract/spec violation;
- auth/permission/security issue;
- data loss/destructive behavior;
- transaction/concurrency bug;
- migration safety;
- public API compatibility;
- serious performance issue;
- missing test only when it hides one of the above.

At most five `BLOCKER`/`HIGH` findings.

Do not make Gemini mechanically re-run formatting/lint/test reasoning or list
MEDIUM/LOW/nits.

If findings exist, Grok fixes only the actionable findings, runs targeted
affected checks and then the full gate once. Do not automatically call Gemini
again.

A second final Gemini review is allowed only if the fix itself changes an
auth/security boundary, public API/contract, migration/data-loss behavior, or
transaction/concurrency architecture.

### 6. READY_FOR_PR

When the gate is green and material review findings are resolved, the manager
may stage intended files, run the git-safety/secret check, commit, push the
feature branch and create/update the PR.

Never merge or auto-merge.

## Escalation

There is no standing advisor/watchdog loop.

Use `watchdog` or `escalation` only when:

1. the same deterministic failure persists after two concrete fixes;
2. authoritative sources directly conflict;
3. a destructive cross-domain/migration decision cannot be resolved from the
   approved contract.

One escalation receives one compact evidence packet. Do not chain reviewers.

## Test budget

Do not add tests for trivial serializer echo or transparent wrappers.

For a changed contract, cover only applicable distinct risks:

- happy path;
- business invariant;
- permission/security boundary;
- validation/error contract;
- transaction/concurrency boundary;
- regression caused by the change.

Prefer parametrization over duplicate service/API matrices.

## Records

Material autonomous interpretations go to `.omp/decisions/`.

Every `VERIFIED` or `BLOCKED` run writes a concise report under
`.omp/reports/` with branch/commit/PR, changed files, exact checks, material
review findings, unresolved decisions and next action.

Do not include full agent transcripts, repeated reasoning, secrets, JWTs,
cookies, provider credentials or sensitive payloads.
