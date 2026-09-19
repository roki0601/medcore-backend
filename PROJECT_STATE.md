# MedCore project state

This is the working state for the project-local OMP orchestration. It is not a
replacement for accepted decisions, architecture documents, feature specs, or
the repository's `AGENTS.md`.

## Current state

- Stage: `COMPLETE`
- Active feature: `001-telegram-auth-account`
- Risk: `HIGH` (authentication/account boundary)
- Spec status: approved; amended to the accepted quorum contract
- Plan status: implemented as written
- Tasks status: T001–T032 complete
- Implementation status: complete on `feature/001-telegram-auth-account`
- Validation status: passed (see `.omp/reports/`)
- Completion status: `VALIDATED`
- Decision record: `.omp/decisions/2026-09-18-001-telegram-auth-account-quorum.md`
- Completion report: `.omp/reports/2026-09-18-001-telegram-auth-account-completion.md`

## Feature order

1. `001-telegram-auth-account`
2. `002-content-catalog-access`
3. `004-content-api-media`
4. `003-learning-state`

Subscription/entitlement behavior is a separate feature boundary. Do not infer
paid semantics from the order above or from a draft document.

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
implementation before running Ruff/pytest. Then run the narrow checks once,
fix locally, and rerun only the failed check. Invoke Luna only when the same
failure persists after two concrete attempts, the investigation loops, or a
source/contract conflict needs an independent read-only opinion. Record the
escalation and its outcome; if the sources still conflict after two bounded
rounds, write `BLOCKED` with evidence and the exact unresolved conflict.

## Next action

Feature 001 is implemented and validated on
`feature/001-telegram-auth-account`; review the diff, commit it, push the
feature branch, and create a PR with the implementation summary and evidence.
Human review and merge are required before starting `002-content-catalog-access`.
Do not start a new feature while this branch is unreviewed. Spec 003 must
implement the User foreign-key `ON DELETE CASCADE` contract stated in the 001
decision record before its learning-owned models ship.

## Source-of-truth pointers

- Backend guardrails: `AGENTS.md`
- Backend architecture: `docs/architecture/`
- Product decisions/context: sibling `../medcore-docs/`
- Feature specs: `specs/`
