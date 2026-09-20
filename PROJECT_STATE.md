# MedCore backend OMP project state

This file tracks the project-local backend workflow. It is not a replacement for
accepted product decisions, approved specs, architecture documents or
`AGENTS.md`.

## Current state

- Stage: `BLOCKED_PENDING_DOCS_MERGE`.
- Active feature: `BE-005` (`005-subscriptions-paywall`).
  - Owner decisions D1–D8 are explicitly approved.
  - Canonical ADR 0009 is proposed in medcore-docs PR #3 and awaits merge to `main`.
  - Backend implementation and spec exist in PR #13.
  - Once ADR 0009 merges into `medcore-docs/main`, backend PR #13 becomes `READY_FOR_REVIEW`.
- Shipped backend feature specs:
  - `001-telegram-auth-account` — merged;
  - `002-content-catalog-access` — merged;
  - `004-content-api-media` — merged;
  - `003-learning-state` — merged;
  - OpenAPI/runtime contract follow-up — merged.
- Pending merge: `005-subscriptions-paywall` (PR #13, awaiting medcore-docs PR #3).
- Later roadmap items BE-006–BE-010 are explicitly BLOCKED until their listed
  owner/upstream decisions exist.
- Human review and merge remain required; auto-merge is forbidden.

## Current validated baseline

Backend 003 learning state and the OpenAPI follow-up are already merged. The
baseline includes:

- Telegram-only auth/session contract;
- catalog + Topic `demo/free/paid` access model;
- synchronous content CRUD/integration contract;
- protected media boundary;
- topic/theory progress;
- flashcard review API;
- resumable quiz attempts and scoring;
- OpenAPI coverage for shipped routes.

Do not reopen these contracts merely because the next feature touches the same
apps.

## Backend roadmap

Use `backend-features/README.md` as the executable queue for work that does not
yet have an approved spec.

Order:

1. BE-005 — subscription core and paid entitlement — `BLOCKED_PENDING_DOCS_MERGE` (impl in PR #13, ADR 0009 in docs PR #3);
2. BE-006 — payment provider integration — `BLOCKED`;
3. BE-007 — dashboard/progress aggregate API — `BLOCKED`;
4. BE-008 — profile/study preferences — `BLOCKED`;
5. BE-009 — content bulk/import extensions — `BLOCKED`;
6. BE-010 — slug-based public URLs — `BLOCKED`.

The briefs already list fixed constraints, exact unresolved decisions, expected
future zones and non-goals. Do not spend model budget rediscovering them.

## BE-005 boundary

Owner decisions D1–D8 are explicitly approved and recorded in
`medcore-docs` PR #3 (ADR 0009: `decisions/0009-subscriptions-core-and-paid-entitlement.md`).
Backend implementation and spec in `specs/005-subscriptions-paywall/` adhere to ADR 0009
and exist in backend PR #13.
The feature transitions to `READY_FOR_REVIEW` as soon as docs PR #3 merges into `main`.

## Token-saving execution rule

For the selected backend feature:

1. read only its feature brief and listed authoritative inputs;
2. confirm those facts against current `main`;
3. do not re-review shipped specs unrelated to the selected boundary;
4. for `READY_FOR_SPEC`, surface only the explicitly listed owner decisions;
5. for implementation-ready work, make a compact module/file zone plan rather
   than another architecture essay;
6. do not spawn routine architect/scout/security/self-review chains.

Normal implementation-ready flow:

`DESIGN(Grok) -> DESIGN_REVIEW(Gemini) -> IMPLEMENT(Grok) -> QUALITY_GATE -> FINAL_REVIEW(Gemini) -> PR`

## Deterministic quality gate

Run the same checks as GitHub CI before final Gemini review:

```text
uv run ruff format --check .
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest --create-db
```

If one command fails, Grok fixes the concrete failure and reruns only that
failed check. After convergence, run the full gate once for final evidence.

## Carry-forward constraints

- The two learning owner decisions remain unresolved:
  score threshold for automatic Topic completion and the long-term policy for
  exposing `correct_answer_ids` after submit. Do not silently close them.
- Paid content remains deny-by-default until BE-005 supplies the entitlement
  source.
- No concrete object-storage provider is selected.
- Capability paths for protected media must not be access-logged.
- Bulk/import, profile/preferences, slug URL migration and dashboard aggregates
  stay blocked until their roadmap brief says otherwise.
- Do not add Celery/Kafka/RabbitMQ without a concrete accepted use case.

## Source-of-truth pointers

- backend guardrails: `AGENTS.md`;
- accepted product decisions: sibling `../medcore-docs/decisions/`;
- shipped implementation contracts: `specs/`;
- backend architecture: `docs/architecture/`;
- not-yet-specified roadmap: `backend-features/`.
