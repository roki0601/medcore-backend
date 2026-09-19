# MedCore project state

This is the working state for the project-local OMP orchestration. It is not a
replacement for accepted decisions, architecture documents, feature specs, or the
repository's `AGENTS.md`.

## Current state

- Stage: `VERIFIED` (implementation + validation); PR open, human review/merge
  pending
- Active feature: `002-content-catalog-access`
- Risk: `HIGH` (content access boundary and paywall composition)
- Spec status: approved via the delegated review
  (`.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md`), spec
  amended to the accepted contract
- Plan status: implemented as written
- Tasks status: T001–T028 complete
- Implementation status: complete on `feature/002-content-catalog-access`
- Validation status: passed (see `.omp/reports/`)
- Completion status: `VERIFIED`
- Decision record: `.omp/decisions/2026-09-19-002-content-catalog-access-quorum.md`
- Completion report: `.omp/reports/2026-09-19-002-content-catalog-access-completion.md`

## Feature order

1. `001-telegram-auth-account` (merged)
2. `002-content-catalog-access` (implemented, PR open)
3. `004-content-api-media`
4. `003-learning-state`

Subscription/entitlement behavior is a separate feature boundary that 002 depends
on: `paid` Topics are unreadable until that feature ships an entitlement source.
Do not infer paid semantics from the order above or from a draft document.

## Preflight record (2026-09-19)

All three repositories were clean and fast-forwarded on `main` before the feature
branch: `medcore-docs` `0b1d51c`, `medcore-backend` `e530c4f`,
`medcore-frontend` `db3473d`.

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

For one task, use one sequential DeepSeek `implementer`. Finish the coherent
implementation before running Ruff/pytest. Then run the narrow checks once, fix
locally, and rerun only the failed check. Invoke Luna only when the same failure
persists after two concrete attempts, the investigation loops, or a
source/contract conflict needs an independent read-only opinion. Record the
escalation and its outcome; if the sources still conflict after two bounded
rounds, write `BLOCKED` with evidence and the exact unresolved conflict.

## Next action

Feature 002 is implemented and validated on
`feature/002-content-catalog-access` (commit `52cae11`); PR
https://github.com/roki0601/medcore-backend/pull/5 is open. Review it, then merge
manually. Human review and merge are required before starting
`004-content-api-media`. Do not push to `main` or merge from the OMP run.

Carry-forward contracts for later features:

- Spec 004 owns media upload/access-url, signed URLs and the storage adapter; 002
  ships only the `media.MediaFile` FK target and never exposes `storage_key`.
- The subscriptions/paywall feature must supply the entitlement source behind
  `apps.subscriptions.policy.has_paid_content_entitlement` before paid content is
  served; do not add a role bypass.
- Spec 003 must implement the learning-owned `ON DELETE CASCADE` foreign keys to
  Topic/Section and the User `ON DELETE CASCADE` contract from the 001 decision
  record before its learning-owned models ship.

## Source-of-truth pointers

- Backend guardrails: `AGENTS.md`
- Backend architecture: `docs/architecture/`
- Product decisions/context: sibling `../medcore-docs/`
- Feature specs: `specs/`