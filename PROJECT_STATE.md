# MedCore project state

This is the working state for the project-local OMP orchestration. It is not a
replacement for accepted decisions, architecture documents, feature specs, or
the repository's `AGENTS.md`.

## Current state

- Stage: `SPEC_REVIEW`
- Active feature: `001-telegram-auth-account`
- Risk: `HIGH` (authentication/account boundary)
- Spec status: present, review required
- Plan status: present but unverified; preserve the existing untracked plan
- Tasks status: not started
- Implementation status: not started
- Validation status: not started
- Completion status: `NEEDS_HUMAN_REVIEW`

## Feature order

1. `001-telegram-auth-account`
2. `002-content-catalog-access`
3. `004-content-api-media`
4. `003-learning-state`

Subscription/entitlement behavior is a separate feature boundary. Do not infer
paid semantics from the order above or from a draft document.

## Required transition gate

The manager must read the complete feature spec, relevant sibling
`medcore-docs` decisions, backend architecture, and current code/tests before
moving beyond `SPEC_REVIEW`. A draft plan is not approval. A `TBD` remains a
blocker until the owner records a decision.

## Retry/escalation

For one task, use one sequential implementation writer:

1. Qwen `implementer`;
2. Luna planning/review and a targeted retry;
3. DeepSeek `architect`/`senior-reviewer` for high-risk or repeated failure;
4. `BLOCKED` with evidence and the exact human decision if it still cannot pass.

## Next action

Run the manager's read-only spec review for `001-telegram-auth-account`. Do not
write product code until the state reaches `READY_FOR_IMPLEMENTATION`.

## Source-of-truth pointers

- Backend guardrails: `AGENTS.md`
- Backend architecture: `docs/architecture/`
- Product decisions/context: sibling `../medcore-docs/`
- Feature specs: `specs/`
