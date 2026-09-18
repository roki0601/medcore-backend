# MedCore project state

This is the working state for the project-local OMP orchestration. It is not a
replacement for accepted decisions, architecture documents, feature specs, or
the repository's `AGENTS.md`.

## Current state

- Stage: `SPEC_REVIEW`
- Active feature: `001-telegram-auth-account`
- Risk: `HIGH` (authentication/account boundary)
- Spec status: present, delegated multi-model review required
- Plan status: present but unverified; preserve the existing untracked plan
- Tasks status: not started
- Implementation status: not started
- Validation status: not started
- Completion status: `AWAITING_MODEL_QUORUM`

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
moving beyond `SPEC_REVIEW`. It must obtain unanimous independent `READY`
verdicts from the Qwen `spec-reviewer`, Luna `watchdog`, and DeepSeek
`architect`. A draft plan is not approval. A `TBD` remains a blocker until the
delegated quorum resolves it from source evidence and writes a record under
`.omp/decisions/`.

High-risk features may proceed without interactive approval only after the full
quorum, a decision record for every material interpretation, and a successful
final DeepSeek review. An unresolved conflict between authoritative sources is
the only source-of-truth hard stop.

## Retry/escalation

For one task, use one sequential implementation writer:

1. Qwen `implementer`;
2. Luna planning/review and a targeted retry;
3. DeepSeek `architect`/`senior-reviewer` for high-risk or repeated failure;
4. Multi-model deliberation with a decision record; if the sources still
   conflict after three rounds, write `BLOCKED` with evidence and the exact
   unresolved conflict.

## Next action

Run the manager's independent multi-model spec review for
`001-telegram-auth-account`. Do not write product code until the quorum and any
required decision records move the state to `READY_FOR_IMPLEMENTATION`.

## Source-of-truth pointers

- Backend guardrails: `AGENTS.md`
- Backend architecture: `docs/architecture/`
- Product decisions/context: sibling `../medcore-docs/`
- Feature specs: `specs/`
