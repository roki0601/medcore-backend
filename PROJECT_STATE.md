# MedCore project state

This is the working state for the project-local OMP orchestration. It is not a
replacement for accepted decisions, architecture documents, feature specs, or the
repository's `AGENTS.md`.

## Current state

- Stage: `VERIFIED` (implementation + validation); PR open, human review/merge
  pending
- Active feature: `004-content-api-media`
- Risk: `HIGH` (integration credential, protected media URLs, concurrency)
- Spec status: approved via the delegated review
  (`.omp/decisions/2026-09-19-004-content-api-media-review.md`), spec amended to
  the accepted contract
- Plan status: implemented as written
- Tasks status: T001–T020 complete
- Implementation status: complete on `feature/004-content-api-media`
- Validation status: passed (see `.omp/reports/2026-09-19-004-content-api-media-completion.md`)
- Completion status: `VERIFIED`
- Decision record: `.omp/decisions/2026-09-19-004-content-api-media-review.md`
- Completion report: `.omp/reports/2026-09-19-004-content-api-media-completion.md`

## Feature order

1. `001-telegram-auth-account` (merged)
2. `002-content-catalog-access` (merged)
3. `004-content-api-media` (implemented, PR open)
4. `003-learning-state`

Subscription/entitlement behavior is a separate feature boundary that 002/004
depend on: `paid` Topics and `paid` media are unreadable until that feature ships
an entitlement source. Do not infer paid semantics from the order above or from a
draft document.

## Preflight record (2026-09-19, feature 004)

All three repositories were clean and fast-forwarded on `main` before the feature
branch: `medcore-docs` `0b1d51c`, `medcore-backend` `d7a9584`,
`medcore-frontend` `db3473d`. Branch `feature/004-content-api-media` was created
from `d7a9584`; delivery commit `a1b3781`.

## Autonomous transition gate

The manager must read the complete feature spec, relevant sibling
`medcore-docs` decisions, backend architecture, and current code/tests before
moving beyond `SPEC_REVIEW`. DeepSeek is the primary model for planning and
implementation. A draft plan is not approval. A `TBD` remains a blocker until
the manager resolves it from source evidence and writes a record under
`.omp/decisions/`.

Luna is not a standing advisor. The manager invokes the read-only Luna watchdog
only for a repeated failure, stalled investigation, serious uncertainty, or a
source/contract conflict, as defined in `.omp/AUTONOMOUS_REVIEW.md`. An
unresolved conflict between authoritative sources is the source-of-truth hard
stop.

## Retry/escalation

Build a dependency-aware zone plan instead of mapping one worker to every task.
Use one DeepSeek `implementer` for one coherent zone, or dynamically launch
`N = min(4, independent zones, available session capacity)` workers in parallel
when their writable files, migrations, fixtures, contracts, and dependency
chains are disjoint. Shared foundations and overlapping zones remain
sequential. Finish each zone before its targeted checks; then run project-wide
Ruff/pytest/Django/migration checks once after
integration. Add tests only for distinct behavior, security/permission,
validation/error, boundary/concurrency, or regression coverage; prefer
parametrization and report the rationale. Invoke Luna only when the same
failure persists after two concrete attempts, the investigation loops, or a
source/contract conflict needs an independent read-only opinion. Record the
escalation and its outcome; if the sources still conflict after two bounded
rounds, write `BLOCKED` with evidence and the exact unresolved conflict.

## Next action

Feature 004 is implemented and validated on
`feature/004-content-api-media` (commit `a1b3781`); PR
https://github.com/roki0601/medcore-backend/pull/6 is open. Review it, then merge
manually. Human review and merge are required before starting
`003-learning-state`. Do not push to `main` or merge from the OMP run.

Carry-forward contracts for later features:

- Spec 003 must ship the learning-owned `ON DELETE CASCADE` foreign keys to
  Topic/Section/Quiz and the User `ON DELETE CASCADE` contract from the 001
  decision record; quiz questions/answers are identity-stable and are never
  deleted by the content API, so 003 owns the attempt-time policy for aggregate
  deletion.
- The subscriptions/paywall feature must supply the entitlement source behind
  `apps.subscriptions.policy.has_paid_content_entitlement` before paid content or
  paid media is served; do not add a role bypass.
- The concrete object-storage provider is still a deployment decision: the local
  backend is refused outside `DEBUG`, and production media upload requires an
  S3-compatible backend configured through the environment.
- Deployments must exclude `/api/v1/media/upload/` and `/api/v1/media/file/`
  from access logs (capability tokens travel in the path) and keep protected
  storage buckets private.
- Slug-based public URLs, bulk endpoints, async import and media processing
  remain out of scope.

## Source-of-truth pointers

- Backend guardrails: `AGENTS.md`
- Backend architecture: `docs/architecture/`
- Product decisions/context: sibling `../medcore-docs/`
- Feature specs: `specs/`
